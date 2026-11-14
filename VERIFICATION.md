# Verification — 14 November 2026

## Automated checks

- Python backend suite: **4 passed** in the local development environment.
- `python -m pip check`: no broken requirements for the installed project environment.
- Deterministic tests isolate provider failures using doubles; the real-provider checks below are separate evidence.
- GitHub Actions runs the backend suite on Python 3.11 without requiring model weights or credentials.

## Real-provider checks

- Fixture baseline and actual local-model runs completed on the same immutable three-case dataset.
- The real model scored 2/3: it wrapped a requested JSON answer in Markdown fences, which correctly failed strict JSON scoring.
- Comparison reported a one-case regression and a failed threshold, rather than hiding the failure.
- Per-case latency, model token counts, traces, persisted results and exports were exercised. Cost remained null.

## Scope

This is a runnable single-user local portfolio implementation. Smoke checks on synthetic/public data are not a production-readiness claim, a general quality benchmark, or proof that an AI output is always correct. See README for supported formats, runtime dependencies and operational boundaries.
