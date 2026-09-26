# foldwise

foldwise learns how you already file things and keeps your machine that way. It sorts new files from Downloads and Desktop into your own folder tree, flags misfiled files and plain-text credentials, and removes duplicates safely. Everything runs on your machine. Nothing moves until you have seen a preview, every run can be undone, and the only delete is a duplicate that has a verified identical copy elsewhere.

## Install

```bash
pip install foldwise              # includes laya and PyTorch
pip install "foldwise[mac]"       # macOS: also read text in images with Vision
```

Python 3.11 or newer, on macOS or Linux. On Linux, install `tesseract` and `exiftool` for image text and metadata; foldwise works without them.

## First ten minutes

```bash
foldwise init            # builds ~/.config/foldwise/taxonomy.yaml from your existing folders
foldwise train           # fine-tune the model on how you already file things (GPU; 1.5 to 2.5 hours)
foldwise sort            # preview where Downloads and Desktop files would go
foldwise review          # choose folders for held files; answers can become rules
foldwise apply           # move exactly what the preview showed
foldwise undo           # reverse the last run
foldwise status          # dashboard
```

`init` reads the folders under `~/Documents` (or the `--root` folders you pass), writes one entry per folder with a description taken from sample filenames, and proposes rules from words that only appear in one folder. Open the file and edit anything that looks wrong. If a folder has more than 8 subfolders, `init` says so: group them under a label so each choice has at most 8 options, which is what the model handles well.

## How a file is decided

In order, the first match wins:

1. In a protected folder: left alone.
2. Byte-identical to a file you already filed: sent to the duplicate review folder.
3. Contains a credential (API keys, private keys, backup codes): sent to your sensitive folder.
4. Matches a rule: sent to the rule's folder.
5. Has a meaningless name (`image.png`, `IMG_1234`, a hex or UUID name): held for review.
6. With fine-tuned models: moved only when every model picks the same folder with enough confidence (0.75 with two models, 0.85 with one). Otherwise held.

Until you run `foldwise train`, step 6 always holds, so a fresh install only moves what rules and duplicates settle.

## Duplicates

```bash
foldwise dedupe          # plan: extra copies go to the review folder
foldwise apply
foldwise dedupe --purge  # delete review-folder files that still have an identical copy elsewhere
```

Purge is the one delete and the one action `foldwise undo` cannot reverse: deletion happens only after a byte-identical twin outside the review folder is re-verified at delete time, so recovery is copying the twin back.

The kept copy is chosen by: a protected folder, then a clean name over `name (1).pdf`, then a real folder over a dump folder, then the shortest path. Folders listed under `snapshots` (backups, archives) are never scanned, because backups are supposed to contain copies.

## Audit

`foldwise audit` checks files you already filed and suggests moves where a rule or the models disagree with where a file sits. Credentials are listed first. Suggestions are never applied unless you run `foldwise apply --include-suggested`. Rules were written for loose files, so read audit suggestions before applying them: a folder you grouped on purpose (a case folder, one client's statements) may look "wrong" to a rule.

## Training a model on your folders

```bash
foldwise train
```

This fine-tunes the laya decision model on your own tree: every filed document is a labeled example. It runs locally on Apple Silicon or a CUDA GPU (about 1.5 to 2.5 hours for roughly 800 files on an M4 Pro) and refuses to start on CPU unless you pass `--force`. It keeps a frozen test set so runs can be compared, trains on harder copies of your files (random names, blank text) so it copes with badly named downloads, and keeps the new model plus the previous one; sort then requires both to agree. Files in your sensitive folder, or containing credentials, train on filename and metadata only. Only one training can run at a time. Each run copies the base checkpoint (about 1.6 GB), so prune older timestamped folders under the models directory when disk space matters; only `previous + new` are ever used.

## Reviewing held files with a local model

```bash
foldwise review --llm ollama              # or lmstudio, or openai (any OpenAI-compatible endpoint)
foldwise review --llm ollama --images     # also send images to a vision model
```

Configure providers in `taxonomy.yaml`. Local servers are the default and need no key:

```yaml
llm:
  ollama: {model: <a model you pulled>}                  # http://localhost:11434
  lmstudio: {model: <the model you loaded>}               # http://localhost:1234/v1
  openai: {base_url: http://host:port/v1, model: <name>, api_key_env: MY_KEY_VAR}
```

If `model` is missing, foldwise lists the models the server has. Before anything is sent it shows how many files and images will go and whether the endpoint is on this machine, and asks for confirmation every time. Text is masked for credentials, and files that contain credentials are never sent. Suggestions are proposals: you accept, edit or reject each one.

## Reviewing held files with your coding agent

Any coding agent that can run commands (Claude Code, Codex, Cursor, and others) can do the review:

```bash
foldwise review --export held.json        # held files: masked text, paths, folder list, answer format
# the agent reads held.json (and opens image paths itself), then writes answers.json
foldwise review --import answers.json     # validated into a plan
foldwise apply
```

Or register foldwise as an MCP server, so the agent can call it directly:

```bash
claude mcp add foldwise -- foldwise mcp
```

For harnesses configured with JSON, add `{"mcpServers": {"foldwise": {"command": "foldwise", "args": ["mcp"]}}}`. The MCP tools are `status`, `list_folders`, `list_held`, `preview_sort` and `propose_moves`. None of them moves files: the agent proposes a plan and you run `foldwise apply`. Answers are checked against what was exported, so an agent can only place files it was shown, and only into folders in your taxonomy.

## Privacy

- Nothing leaves your machine unless you point a review provider at a remote endpoint and confirm that run. Ollama and LM Studio run locally.
- Credentials are masked in previews, logs and the extraction cache, excluded from training text, and never sent to an LLM.
- Your fine-tuned models stay on your machine. foldwise never uploads them.

## Files

- Config: `~/.config/foldwise/taxonomy.yaml` (Linux) or `~/Library/Application Support/foldwise/taxonomy.yaml` (macOS).
- State: plans, journals (for undo), the extraction cache, the frozen test set and models, in the platform data folder.
- Set `FOLDWISE_HOME` to keep both under one folder.

## Credits

foldwise runs [laya](https://github.com/NandhaKishorM/laya) checkpoints by Convai Innovations, and its training loop is adapted from laya's fine-tuning notebook. Both are Apache-2.0.
