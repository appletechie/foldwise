# foldwise: design spec

Status: draft for review, 2026-09-25. Working name `foldwise` (free on PyPI as of today).

## 1. Purpose

An open-source, local-first CLI that learns how a person already files things, then keeps their machine organized: it sorts new files into their own folder tree, audits misfiled files, and removes duplicates safely. Everything runs on the user's machine; an LLM is optional.

It generalizes a working private prototype (`~/Developer/1_Projects/file-organizer`) that sorted 131 files, audited 688 filed files, removed verified duplicates, and fine-tuned laya three times.

**Audience (decided):** developers and power users comfortable with a terminal, on Apple Silicon or a CUDA GPU for training. No GUI in v1.

**Platforms (decided):** macOS and Linux. Windows later.

**Model (decided):** laya with PyTorch is a required dependency. Fine-tuning laya on the user's own tree is the core of the product, not an add-on.

**LLM review (decided):** optional and local-first. Built-in providers: Ollama, LM Studio, and any OpenAI-compatible endpoint. A coding agent the user already runs (Claude Code, Codex, Cursor, and so on) can also do the review, through a JSON export/import on the CLI or through foldwise's MCP server. There is no built-in cloud provider. The tool is fully usable with no LLM at all.

### Success criteria for v1

1. `pip install foldwise`, then `foldwise init` on a real home directory produces a valid taxonomy and a preview in under 5 minutes, with no model training and no network.
2. `foldwise sort` never overwrites a file, never moves anything without a preview or an explicit `--apply`, and every applied run can be reversed with `foldwise undo`.
3. On the maintainer's own tree, `foldwise train` reproduces the prototype's result: at least 50% of normally named held-out files auto-move at 95% or better precision.
4. `foldwise dedupe` never deletes a file unless a byte-identical copy is verified to exist outside the review folder at delete time.
5. No file content leaves the machine unless the user points a provider at a non-local endpoint and confirms that specific run. Local endpoints (Ollama, LM Studio) are the default.
6. CI passes on macOS and Ubuntu with no network access in unit tests.
7. `foldwise mcp` runs a stdio MCP server that a coding harness can register (for example `claude mcp add foldwise -- foldwise mcp`); its tools read state and write plans, and never move files.

### Non-goals for v1

GUI or desktop app, Windows, background watcher daemon, a built-in cloud LLM provider, cloud sync, near-duplicate (perceptual) image matching, publishing anyone's fine-tuned model, sorting inside git repositories.

## 2. Requirements carried from the prototype

Each line is a failure or finding from the prototype and the rule it becomes.

| Finding | Requirement |
|---|---|
| Stock laya put 11% of files in the right folder | Zero-shot laya is never trusted alone: rules first, a fine-tuned model second, holds for the rest |
| Rules handled most real sorting | Rules are first-class config, with a command that proposes them from existing folders |
| Rules misfired on deliberately grouped folders during audit | Rules apply to loose files only; `audit` shows rule hits as suggestions and never applies them in bulk |
| 32-way project choice scored 4/55; grouping into 7 families fixed the family level | Validate the taxonomy: warn when any node has more than 8 children and offer to group them |
| Training set was 60% project files and biased the model | Per-folder caps and a per-group cap, and a report of the class balance before training |
| v1 and v2 used different test sets, so they couldn't be compared | One frozen test set per install, reused by every training run |
| Meaningless filenames: v2 was about 69% right at 0.85 confidence | Hold meaningless names (UUID, hex, `image`, `IMG_1234`, and so on) unless a rule matches |
| Two models agreeing at 0.75: 97% right, 51% auto-moved; one model at 0.85: 94% right | Keep the previous and current model; a move requires every model to agree at 0.75, or 0.85 when only one model exists |
| Backups duplicate live files; dedupe picked the backup as keeper | Snapshot roots (archives, backups) are excluded from dedupe by default |
| Real API keys found in notes, plans, and a CSV | Secret detection: matching files route to the sensitive folder, are excluded from training content, and are never sent to an LLM |
| macOS Vision hung for 21 minutes on one file | Every extractor call has a timeout |
| Two concurrent trainings exhausted 26 GB of RAM | A lock file allows one training at a time; batch size is chosen from available memory |
| A preview printed a secret in full | Previews and logs mask anything the secrets detector matches |
| Stale plan looked pending after it was applied | A plan records its applied state; the dashboard reads it |

## 3. Architecture

One Python package, one entry point (`foldwise`), small modules with one job each.

```
foldwise/
  cli.py            argument parsing, command dispatch (typer)
  config.py         load, validate, save taxonomy.yaml; defaults; path expansion
  paths.py          XDG / Application Support locations for config, state, models
  inventory.py      walk roots and inboxes, apply exclude/protect, yield Items
  extract/
    base.py         Extractor protocol, timeout wrapper, secret masking
    text.py         plain text, office (docx/xlsx/pptx via zipfile), zip listing, pdf
    macos.py        Vision OCR and scene labels (pyobjc), Spotlight metadata (mdls)
    linux.py        Tesseract OCR (pytesseract), exiftool metadata; skipped when missing
  secrets.py        secret patterns, masking, "is sensitive" decision
  rules.py          rule matching (name, content, extension), rule proposal
  classify.py       pipeline: excluded, duplicate-of-filed, rule, name gate, model ensemble
  model.py          load laya Agents, hierarchical descent, agreement, confidence
  plan.py           Plan, PlanItem; write/read plan files; applied state
  mover.py          apply plan with journal, collision-safe names, undo
  dedupe.py         size-then-hash grouping, keeper ranking, verified purge
  train/
    dataset.py      labeled files from the tree, caps, frozen test split, variants, oversampling
    loop.py         RLCD training loop (adapted from laya's notebook, Apache-2.0)
    evaluate.py     full-path accuracy, coverage at 95% precision, masked-name robustness
  llm/
    base.py         prompt, answer schema, parsing, size estimate, local/remote check
    openai_compat.py LM Studio and any OpenAI-compatible endpoint (standard-library HTTP)
    ollama.py       local Ollama (standard-library HTTP)
  agent.py          export held files for a coding agent, validate and import its answers
  mcp_server.py     stdio MCP server: status, list_folders, list_held, preview_sort, propose_moves
  tui/
    status.py       dashboard (rich)
    review.py       interactive review of held items and proposed rules (rich prompts)
```

Dependencies (all required): `laya` (brings PyTorch), `mcp`, `typer`, `rich`, `pyyaml`, `platformdirs`, `pypdf`. One extra: `foldwise[mac]` (pyobjc-framework-Vision, pyobjc-framework-Quartz). On Linux, OCR and metadata call the `tesseract` and `exiftool` binaries when installed. LLM providers use standard-library HTTP, so they add no dependency. The Swift OCR helper from the prototype is replaced by pyobjc so nothing needs compiling at install.

Interfaces between units:

- `inventory.items(config) -> Iterator[Item]`, where `Item(path, kind: "inbox" | "filed", is_dir)`.
- `extract.read(path, timeout) -> Extracted(text, metadata, source: "ocr" | "text" | "none")`, never raising.
- `classify.decide(item, extracted, ctx) -> Decision(action: "move" | "hold", dest, reason, confidence)`.
- `plan.Plan` is a JSON file of `PlanItem(src, dest, reason, confidence, action)` plus `created`, `applied_at`, and `command`.
- `mover.apply(plan) -> Journal` and `mover.undo(journal)`.

## 4. Configuration and state

`~/.config/foldwise/taxonomy.yaml` (hand-editable, commented):

```yaml
version: 1
inboxes: [~/Downloads, ~/Desktop]
roots: [~/Documents, ~/Developer/Projects]   # the organized tree; training data comes from here
exclude: [~/Documents/Codex]                 # never read, never moved
protect: [~/Documents/Areas/Legal/Sensitive] # never moved out of, may be a dedupe keeper
snapshots: [~/Documents/Archives]            # ignored by dedupe, labels only
sensitive_dest: ~/Documents/Areas/Legal/Sensitive
review_dir: ~/Documents/Archives/Duplicate-Review   # duplicates wait here until `dedupe --purge`
repos: hold                                   # files routed into a git repo are held
policy:
  min_confidence: 0.75          # with two or more models, all must agree
  min_confidence_single: 0.85   # used when only one fine-tuned model exists
  hold_meaningless_names: true
tree:                                         # generated by init, edited by the user
  ~/Documents/Areas:
    desc: ongoing responsibilities: businesses, finances, legal
    children:
      ~/Documents/Areas/Finances: {desc: taxes, bank statements, invoices}
rules:
  - {match: name, pattern: '(?i)tax return|1099', dest: ~/Documents/Areas/Finances}
```

Grouping nodes (families) are keys without a path, as in the prototype, and validated to contain at least one real folder.

State lives in the platform data dir (`~/Library/Application Support/foldwise` or `~/.local/share/foldwise`): `cache/extract.jsonl` (keyed by path, size and mtime; content capped at 6000 characters; secrets masked), `test_set.json`, `plans/`, `journal/`, `models/<name>/`, `train.lock`, `logs/`.

## 5. Commands and data flow

`foldwise init`: walks `roots`, builds `tree` from existing folders two or three levels deep with a description from sampled filenames, flags nodes with more than 8 children, proposes rules from filename patterns that are frequent within one folder and rare elsewhere, and writes `taxonomy.yaml` for review. Offers a PARA starter tree when the roots are empty. No network.

`foldwise sort [--apply] [--path P]`: inventory, then extract with the cache, then classify, then write a plan and print the preview. `--apply` runs the mover on the move items of that plan. The default is preview only.

`foldwise apply [PLAN]`: applies the latest (or a named) plan exactly as written, after the user has reviewed or edited it.

`foldwise undo [JOURNAL]`: reverses the latest (or a named) applied journal, skipping entries whose destination is gone or whose source path is occupied.

`foldwise review`: lists held items. Four ways to decide them, all ending in a plan the user applies:
- Interactive (default): choose a folder for each; each answer optionally becomes a rule.
- `--llm ollama|lmstudio|openai`: shows the file count and whether the endpoint is local, asks for confirmation, sends masked content (images only with `--images`), and presents suggestions to accept, edit or reject. Accepted filenames can become rules.
- `--export FILE` / `--import FILE`: writes the held files (masked text, paths, folder list, answer schema, instructions) for a coding agent, then validates the agent's answers against the saved export: only exported file ids and existing taxonomy folders are accepted.
- The MCP server (below) offers the same exchange as tools.

`foldwise mcp`: stdio MCP server for coding harnesses. Tools: `status`, `list_folders`, `list_held`, `preview_sort` (writes a sort plan, moves nothing), `propose_moves` (validated like `--import`, writes a review plan). There is no tool that moves files; the agent tells the user to run `foldwise apply`.

`foldwise audit [PATH...]`: classifies filed files and writes a plan of disagreements marked `suggested`, which is never applied in bulk without review. Secret hits are listed first.

`foldwise dedupe [PATH...] [--purge]`: groups by size, then SHA-256, ranks the keeper (protected, then clean name, then not in a dump folder, then shallowest), and plans extras into the review folder. `--purge` deletes review-folder files only after re-verifying at that moment that a byte-identical copy exists outside it.

`foldwise train [--base english]`: acquires the lock, builds the dataset, prints class balance and time estimate, evaluates the current models on the frozen test set, trains, calibrates, evaluates, and keeps the new model plus the previous one as the ensemble. Refuses on CPU-only machines unless `--force`, because it would take many hours.

`foldwise status`: the dashboard from the prototype (tree with counts and untracked folders, waiting items, last plan and whether it was applied, move history with undo commands, models and scores).

## 6. Classification pipeline

In order; the first that decides wins:

1. Excluded or protected path: skip.
2. Byte-identical to a filed file (size index, then hash): move to `review_dir`.
3. Secret detected in content: move to `sensitive_dest`.
4. Rule match (name, content or extension): move to the rule's destination.
5. Meaningless filename and `hold_meaningless_names`: hold.
6. Model ensemble: hierarchical descent through `tree`. At every level each model predicts; disagreement means hold; the running minimum confidence below the threshold means hold (`min_confidence` with two or more models, `min_confidence_single` with one); a destination inside a git repo means hold.
7. Otherwise: move to the chosen leaf.

Without a fine-tuned model, step 6 holds everything and the preview recommends `foldwise train`. Stock laya scored 11 to 18% full-path accuracy in the prototype, so it is never used to move files.

## 7. Safety model

- **Preview by default:** nothing moves unless `--apply` or `apply` is used.
- **Journal:** every move is appended and flushed to the journal before the next one; an interrupted apply can be undone up to the last completed move.
- **No overwrite:** collisions get `name (n).ext`, counted from the original name.
- **No deletes** outside `dedupe --purge`, which verifies again at the moment it deletes.
- **Secrets:** masked in previews, logs and cache, excluded from training content, never sent to an LLM.
- **Timeouts:** 30 seconds per extractor call by default; a timeout means no text.
- **One training at a time:** a lock file, plus batch size chosen from memory: 4 below 48 GB (verified on 26 GB), 8 at 48 GB or more.
- **LLM runs:** show what will be sent (file count, whether images are included) and whether the endpoint is on this machine, and require confirmation each time.
- **Agents:** exports contain masked text only and withhold files with credentials. Imports accept only file ids from the saved export and folders from the taxonomy; paths in an agent's answer are ignored. MCP tools never move files and never print to stdout (which carries the protocol).

## 8. Training

Carried from the prototype with its measured defaults: at most 60 files per folder and 8 per repo; frozen test set of one fifth of each folder with at least 3 files; 50% of training files get a harder copy (random filename or blank content); folders under 8 examples are repeated with fresh copies; 3 epochs; batch 4 with gradient accumulation 4; soft targets 0.95; RLCD loss as in laya's notebook; per-type temperature refit on a held-out calibration slice. Reports full-path accuracy, coverage at 95% precision, and random-filename robustness, and compares against the current models on the same frozen set.

The English checkpoint is the default base. Multilingual is available through `--base multilingual`; it scored lower in the prototype (57% vs 63%) and is only recommended for non-English file content.

## 9. Testing

- Unit: rules, secrets masking, name gate, keeper ranking, collision naming, taxonomy validation, plan and journal round trip, undo after partial apply, extractor timeouts (with a fake slow extractor).
- Integration: a synthetic tree fixture (about 60 files across 8 folders, including duplicates, a snapshot folder, a secret file and meaningless names) running init, sort, apply, undo, dedupe and purge, and asserting the tree afterwards.
- Model: one slow test that trains on the fixture for one step with a tiny config, marked `slow` and skipped in CI.
- CI: GitHub Actions on macOS and Ubuntu, Python 3.11 to 3.14, no network (laya is mocked in unit tests).

## 10. Packaging and release

`pyproject.toml` with the `foldwise` console script and the extras above. Apache-2.0 license, matching laya, with a NOTICE crediting the laya fine-tuning notebook. README covers install, the first 10 minutes (`init`, `sort`, `review`, `apply`, `undo`), training requirements, and a privacy section. Releases go to PyPI through GitHub trusted publishing.

## 11. Dogfooding

The first real user is the maintainer's own tree. A one-off script (not part of the package) converts the prototype's `taxonomy.json`, rules, frozen test set, and two models into foldwise's config and state, so release candidates are checked against known results (success criterion 3).

## 12. Open questions

1. Final project name (working name `foldwise`).
2. GitHub owner for the repo (personal account or an organization).
3. Publish the prototype's benchmark numbers (accuracy and coverage only, no filenames or folder names) in the README?
