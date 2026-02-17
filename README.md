# Chain of Thoughts

Write prompt text, generate PT-based music, and export MIDI.

This repository turns a sequence of prompt files into a stitched multi-instrument composition by:

1. calling OpenAI Responses API with a strict JSON schema,
2. posting generated features to the DCN server,
3. auto-wrapping features into particles,
4. executing particles to get note streams,
5. stitching all units into one composition JSON,
6. optionally exporting a `.mid` file.

## What You Get

Each run writes a suite folder under `runs/<timestamp>_suite/` containing:

- `composition_suite.json`
- `schedule.json`
- `pt_journal.json`
- `prompts_and_summaries.txt`
- `manifest.json`
- `checkpoint.json`
- `units/*.json`
- optionally `composition_suite.mid`

## Requirements

- Python 3.10+
- Node.js 18+ (for MIDI export)
- A reachable DCN API server
- OpenAI API key

Install Python deps:

```bash
pip install -r requirements.txt
```

Install Node deps (one-time, for MIDI):

```bash
npm install
```

## Configuration

### 1) OpenAI API key

Create `secrets.py` in repo root:

```python
OPENAI_API_KEY = "sk-..."
```

Or set `OPENAI_API_KEY` in your shell.

### 2) DCN account key (optional)

If `PRIVATE_KEY` is set, it is used for DCN auth.
If not set, the run creates a temporary account.

```bash
export PRIVATE_KEY=0x...
```

### 3) DCN API endpoint

Current endpoint is defined in `pt_config.py` (`API_BASE`).
If you need local dev server, change it there.

### 4) Instrument setup

Default config file is `instruments.json`.
You can override with:

```bash
export INSTRUMENT_CONFIG=/absolute/path/to/instruments.json
```

## Prompt Files

Put prompt files in:

- `prompts/user/*.txt`
- `prompts/user/*.template.json` (also supported)

Files are processed in lexicographic order.
Use names like `001.txt`, `002.txt`, etc.

Supported inline directives in prompt text:

- `METER: <num>/<den>` (e.g. `METER: 3/4`)
- `BAR_TICKS: <int>`

If neither is provided, default is 12 ticks (3/4 on 1/16 grid).

## Quick Start

Run all prompt files:

```bash
python3 compose_suite.py
```

Run a subset:

```bash
ONLY=001.txt python3 compose_suite.py
ONLY='00?.txt' python3 compose_suite.py
```

Resume an interrupted suite:

```bash
python3 compose_suite.py --resume runs/<timestamp>_suite
```

## Model Settings

Defaults:

- `OPENAI_MODEL=gpt-5.2`
- `OPENAI_REASONING_EFFORT=medium`

Override example:

```bash
OPENAI_MODEL=gpt-5.2 OPENAI_REASONING_EFFORT=high python3 compose_suite.py
```

Reasoning summaries are printed when the model response completes (not token-streamed live by current implementation).

## Context Chaining Controls

The generator can include prior model JSON bundles as context for continuity.

CLI flags:

- `--context-last all|N` (default `all`)
- `--context-budget <chars>` (default `15000`)

Equivalent env vars:

- `CONTEXT_LAST`
- `CONTEXT_BUDGET_CHARS`

Examples:

```bash
python3 compose_suite.py --context-last 1
python3 compose_suite.py --context-last all --context-budget 30000
CONTEXT_LAST=0 python3 compose_suite.py
```

## Checkpointing and Partial Outputs

Checkpoint/partial settings:

- `--checkpoint-every <K>` (default 5)
- env var `CHECKPOINT_EVERY`

Partial files:

- `composition_suite.partial.json`
- `schedule.partial.json`

## MIDI Export

Automatic MIDI export runs at the end unless disabled.

Disable MIDI export:

```bash
NO_MIDI=1 python3 compose_suite.py
```

Create MIDI later from an existing run:

```bash
node tools/pt2midi.js runs/<timestamp>_suite/composition_suite.json runs/<timestamp>_suite/composition_suite.mid
```

## DCN Preflight and Transformations

At startup, the runner checks `/feature`, `/particle`, `/execute` and ensures required transformations exist.

Required transformation names:

- `add`
- `subtract`
- `mul`
- `div`

By default, missing ones are auto-created.

Disable auto-bootstrap:

```bash
DCN_AUTO_BOOTSTRAP_TRANSFORMS=0 python3 compose_suite.py
```

## End-to-End Example

```bash
cd chain-of-thoughts
pip install -r requirements.txt
npm install

# Optional: stable account
export PRIVATE_KEY=0x...

# Run only first prompt
ONLY=001.txt python3 compose_suite.py
```

## Troubleshooting

### `Auth failed — missing tokens`

- Confirm DCN server is reachable and `/nonce/<address>` + `/auth` work.
- Confirm your `PRIVATE_KEY` format (if set).

### `Failed to parse feature`

- Usually means payload mismatch with server schema.
- This repo already strips internal fields before posting; if this reappears, inspect `runs/<suite>/errors/*.server.txt`.

### Missing `.mid` file

- Make sure you did **not** run with `NO_MIDI=1`.
- Install Node deps with `npm install`.
- If needed, run `tools/pt2midi.js` manually.

### `Cannot find module 'jzz'`

```bash
npm install
```

### Preflight failures

- Check `API_BASE` in `pt_config.py`.
- Verify DCN server supports required endpoints.

## Key Files

- `compose_suite.py`: orchestration, checkpointing, stitching, optional MIDI export
- `pt_generate.py`: single-unit generation + DCN post/execute pipeline
- `dcn_client.py`: auth, preflight, feature/particle/execute/transformation calls
- `pt_config.py`: API base + instrument loading
- `pt_prompts.py`: prompt loading, directives, meter/ticks injection
- `execute_normalize.py`: execute response normalization and validation

## License

MIT
