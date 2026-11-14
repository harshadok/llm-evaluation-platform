# LLM Evaluation Platform

Run repeatable evaluations over immutable dataset versions, score outputs, inspect traces, and detect quality/error/latency regressions.

**Implemented local portfolio application**, with source, persistent storage, runnable API, synthetic examples, automated tests, and a demo script. The interactive API at `/docs` is the included client. This repository does not claim a production deployment, a native mobile client, or previously measured customer usage.

## Features

- Immutable, content-hashed datasets with monotonically increasing versions per name.
- Real Ollama runs and explicitly labelled fixture runs.
- Exact, substring, JSON Schema, and structured tool-call scorers.
- Per-case output, latency, token usage when supplied, failure details, and traces.
- Provider errors score zero and remain in aggregate denominators.
- Same-dataset baseline comparisons with score-drop, error-count, and optional latency thresholds.
- Persistent runs, JSON/CSV exports, and CSV formula escaping. Cost remains null when pricing is unknown.

## Install and run

Use Python 3.9–3.12 (developed/tested here with 3.9.6; Python 3.11 is recommended for a new environment).

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

For AI operations, install [Ollama](https://ollama.com/download), start its local server, and pull a model:

```sh
ollama serve
# In a second terminal:
ollama pull qwen2.5:1.5b
export AI_MODEL=qwen2.5:1.5b
./scripts/start.sh
```

Open [interactive API docs](http://127.0.0.1:8104/docs). The default service port is 8104; override with `PORT`. Keep one API worker bound to localhost. This single-user application has no authentication and stores development data in ignored `data/`; do not expose it as a multi-user public service.

Configuration is read from environment variables. `.env.example` documents them but is not automatically executed or loaded. `OLLAMA_BASE_URL` defaults to `http://127.0.0.1:11434`; `AI_MODEL` selects the installed local model. Providers run on the backend computer; the initial model downloads need internet. No paid API credentials are required.

`requirements.txt` contains portable version ranges; `requirements-lock.txt`, when present, records the exact versions installed in this macOS development environment.

## Walkthrough

1. `POST /datasets` with `examples/dataset.json`. Identical submissions return the same ID; changed content creates a new version.
2. `POST /runs` with `{"dataset_id":"...","provider":"fixture"}` for a deterministic control, or `provider:"ollama"` for a real model.
3. Configure optional `model`, `prompt` (literal `{input}` replacement), and `max_tokens` on a run.
4. Inspect `/runs/{id}`, `/runs/{id}/traces`, and `/runs/{id}/export?format=json` or `csv`.
5. `POST /comparisons` with `baseline_id`, `candidate_id`, optional `max_score_drop`, and optional `max_latency_increase_ms`.
6. Compare only completed runs of the same immutable dataset version. A real model may fail a fixture baseline; that is a recorded quality regression, not an infrastructure success claim.

With the API running, execute the synthetic walkthrough in another terminal:

```sh
source .venv/bin/activate
python scripts/demo.py
```

Use `--url http://127.0.0.1:PORT` to target a different local port. `/docs` exposes the full request and response schemas for manual testing.

## Tests

```sh
python -m pytest -q
```

The current automated suite has **4 passing tests** covering workflow behaviour and important failures. Tests inject provider doubles to remain deterministic; `VERIFICATION.md` separately records real-provider checks. Automated CI runs the deterministic suite without model credentials. The synthetic demo is not a production accuracy benchmark.

## Observability and reproducibility

Every case records start/completion/failure trace events, prompt input, output, scorer, latency, available token usage and errors. A run stores its dataset digest/version and model/prompt configuration. Comparison requires matching dataset digests, so changing the test set cannot silently improve a comparison.

The three-case `examples/dataset.json` is a small synthetic smoke dataset. Use larger held-out datasets for meaningful quality conclusions. Dataset records are immutable; experiment outputs and traces are stored locally.

Modules: `app/main.py` contains schemas, scorers, dataset versioning, run orchestration, comparisons, and export.

## Operational boundaries

- Up to 30 cases per dataset. Runs execute synchronously and save progress after every case; an interrupted process can leave a visible `running` run. There is no distributed queue or automatic resume.
- Fixture results are control data, never labelled as model performance. Output-scorer semantics are deterministic and intentionally strict: Markdown fences fail a strict JSON output check.
- JSON Schema references are disabled to prevent scoring from fetching external schemas. Tool-call scoring compares parsed name/arguments.
- No model-judge or human-label scoring UI is included. Measured smoke results are not a general benchmark of a model's capabilities.
- Token usage is null when not returned; cost is null because local inference has no configured pricing model. Do not interpret null as zero cost.

## Technical references

- [FastAPI](https://fastapi.tiangolo.com/)
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
