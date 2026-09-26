"""RLCD fine-tuning adapted from laya's Kaggle notebook (Apache-2.0, see NOTICE), for one local device."""
import json
import random
import shutil
import time
from pathlib import Path

GROUP_SIZE, SIGMA_START, SIGMA_END = 4, 0.4, 0.1
LR_ENCODER, LR_HEAD = 2e-5, 1e-4


def collate(items: list[dict], pad_id: int) -> dict:
    import torch

    n, length = len(items), max(len(it["ids"]) for it in items)
    kmax = max(len(it["markers"]) for it in items)
    b = {"input_ids": torch.full((n, length), pad_id), "attention_mask": torch.zeros((n, length), dtype=torch.long),
         "marker_pos": torch.zeros((n, kmax), dtype=torch.long),
         "marker_mask": torch.zeros((n, kmax), dtype=torch.bool), "target": torch.zeros((n, kmax)),
         "qtype": torch.tensor([it["qtype"] for it in items])}
    for i, it in enumerate(items):
        b["input_ids"][i, :len(it["ids"])] = torch.tensor(it["ids"])
        b["attention_mask"][i, :len(it["ids"])] = 1
        k = len(it["markers"])
        b["marker_pos"][i, :k] = torch.tensor(it["markers"])
        b["marker_mask"][i, :k] = True
        b["target"][i, :k] = torch.tensor(it["target"])
    return b


def fit_temp(pairs: list[tuple[list[float], list[float]]]) -> float:
    import torch

    kmax = max(len(z) for z, _ in pairs)
    logits, targets = torch.full((len(pairs), kmax), -1e4), torch.zeros((len(pairs), kmax))
    for i, (z, t) in enumerate(pairs):
        logits[i, :len(z)], targets[i, :len(t)] = torch.tensor(z), torch.tensor(t)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = -(targets * torch.log_softmax(logits / log_t.exp(), -1)).sum(-1).mean()
        loss.backward()
        return loss

    opt.step(closure)
    return float(torch.clamp(log_t.exp(), 0.1, 10.0))


def train_model(items: list[dict], calib: list[dict], base: Path, model_cfg: dict, tok, device: str, out: Path,
                rng: random.Random, epochs: int = 3, micro_batch: int = 4, grad_accum: int = 4, log=print) -> None:
    import torch
    from laya.common import QTYPES, build_model, proper_reward
    from safetensors.torch import load_file, save_file

    model = build_model(model_cfg, encoder_dir=str(base / "encoder"))
    model.load_state_dict(load_file(str(base / "model.safetensors")), strict=True)
    model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.head_checkpointing = True
    model.to(device).train()
    enc = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    head = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    opt = torch.optim.AdamW([{"params": enc, "lr": LR_ENCODER}, {"params": head, "lr": LR_HEAD}], weight_decay=0.01)
    updates = max(1, len(items) // (micro_batch * grad_accum) * epochs)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=updates, eta_min=1e-6)
    t0 = time.time()
    for epoch in range(epochs):
        rng.shuffle(items)
        sigma = SIGMA_START + (SIGMA_END - SIGMA_START) * epoch / max(1, epochs - 1)
        total, steps = 0.0, 0
        for s in range(0, len(items), micro_batch):
            b = {k: v.to(device) for k, v in collate(items[s:s + micro_batch], tok.pad_token_id).items()}
            logits, act = model(b["input_ids"], b["attention_mask"], b["marker_pos"], b["marker_mask"], b["qtype"])
            mask, target = b["marker_mask"], b["target"]
            k = mask.sum(-1, keepdim=True).float()
            eps = torch.randn((GROUP_SIZE,) + logits.shape, device=device) * sigma * mask
            eps = (eps - eps.sum(-1, keepdim=True) / k) * mask
            z = logits.detach().unsqueeze(0) + eps
            q = torch.softmax(z.masked_fill(~mask, -1e4), -1)
            with torch.no_grad():
                r = proper_reward(q, target.unsqueeze(0), b["qtype"], mask, w_sph=0.75, w_rps=1.0)
                centered = r - r.mean(0, keepdim=True)
                adv = centered / (centered.std() + 1e-6)
            logp = -(((z - logits.unsqueeze(0)) ** 2) * mask).sum(-1) / (2 * sigma ** 2)
            loss_ce = -(target * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).mean()
            loss = (-(adv * logp).mean() + loss_ce) / grad_accum + 0.0 * act.sum()
            loss.backward()
            steps += 1
            total += loss.item() * grad_accum
            if steps % grad_accum == 0 or s + micro_batch >= len(items):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
            if steps % 50 == 0:
                log(f"  epoch {epoch + 1}/{epochs} step {steps}/{-(-len(items) // micro_batch)} "
                    f"loss {total / steps:.4f} ({time.time() - t0:.0f}s)")
        log(f"epoch {epoch + 1} done, loss {total / max(1, steps):.4f}, {time.time() - t0:.0f}s")

    model.eval()
    pairs = []
    with torch.no_grad():
        for s in range(0, len(calib), 16):
            chunk = calib[s:s + 16]
            b = {k: v.to(device) for k, v in collate(chunk, tok.pad_token_id).items()}
            lg = model(b["input_ids"], b["attention_mask"], b["marker_pos"], b["marker_mask"], b["qtype"])[0]
            lg = lg.float().cpu()
            pairs += [(lg[i, :len(it["markers"])].tolist(), it["target"]) for i, it in enumerate(chunk)]
    temps = list(model_cfg.get("temperature", [1.0, 1.0, 1.0]))
    if len(pairs) >= 10:
        temps[QTYPES["choice"]] = fit_temp(pairs)

    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(base, tmp, ignore=shutil.ignore_patterns("multilingual", "typed-decisions", "model.safetensors",
                                                             "rl_agent_config.json"))
    save_file({k: v.half().contiguous().cpu() for k, v in model.state_dict().items()}, str(tmp / "model.safetensors"))
    saved_cfg = {**model_cfg, "fine_tuned": True, "model_name": f"foldwise-{out.name}", "temperature": temps}
    saved_cfg.pop("temperature_by_options", None)  # a per-type refit; inherited buckets would override it
    (tmp / "rl_agent_config.json").write_text(json.dumps(saved_cfg, indent=2))
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    log(f"saved {out}")
