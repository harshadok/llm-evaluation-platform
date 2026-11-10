# LLM Evaluation Platform

**Status: Planning / documentation only.** This repository currently contains a project specification and implementation roadmap. No working application, provider integration, deployment, or measured results are included yet.

A personal learning project by [Harshad Odakkal](https://github.com/harshadok), building on professional Flutter and mobile engineering experience while transitioning toward AI/mobile engineering.

## Problem and goal

Compare prompt and model configurations against repeatable datasets and inspect quality regressions, latency, and cost.

## Skills to practise

- LLM evaluation
- Regression testing
- Observability
- AI quality assurance
- Experiment comparison

## Planned end-to-end workflow

1. Create a versioned dataset of prompts, reference answers, and scoring rules.
2. Register a prompt and model configuration for an experiment.
3. Run dataset cases and record outputs, errors, latency, and token usage where available.
4. Score deterministic cases with explicit rules and optionally collect labelled model-judge scores.
5. Compare candidate results with a saved baseline using explicit regression thresholds.
6. Inspect traces and export a report for human review.

## Proposed architecture

Python evaluation runner and API; provider adapters; relational experiment store; structured trace events; Flutter results dashboard.

The stack is a design proposal. Specific providers, libraries, model versions, and database products will be selected and documented during implementation.

## Planned API surface

- `POST /datasets` — register a versioned dataset
- `POST /runs` — launch an evaluation run
- `GET /runs/{id}` — inspect results and traces
- `POST /comparisons` — compare a candidate against a baseline

These endpoints are proposed contracts; they are not implemented.

## Core data model

Dataset(version, cases); Run(dataset_version, config, status); CaseResult(output, score, latency_ms, usage, error); Comparison(baseline, candidate, thresholds, regressions).

## Flutter/mobile experience

Run history, baseline selection, score comparison, failing-case inspection, and latency or usage summaries.

## Evaluation and acceptance plan

- [ ] Use fixed outputs to verify scorers and regression thresholds.
- [ ] Record dataset and prompt versions so comparisons are traceable.
- [ ] Test failed provider calls, missing usage fields, and partially completed runs.
- [ ] Distinguish model-judge scores from deterministic checks and human review.
- [ ] Verify aggregate scores include error cases and preserve case-level detail.

No accuracy, latency, cost, or reliability results have been measured. Results will be added only after reproducible runs.

## Implementation roadmap

- [ ] **Milestone 1:** Define a small versioned dataset and deterministic scoring rules.
- [ ] **Milestone 2:** Build a provider-independent run interface with recorded outputs and errors.
- [ ] **Milestone 3:** Add experiment storage, traces, and baseline comparisons.
- [ ] **Milestone 4:** Build the Flutter results dashboard and exportable reports.
- [ ] **Milestone 5:** Use the platform to evaluate one other portfolio project and publish measured findings.

## Planned demonstration

Compare two prompt configurations on a small dataset and inspect an intentionally introduced regression alongside the underlying output and trace.

## Data and operational boundaries

Do not publish secrets or sensitive prompts in traces. Model-judge scores are estimates rather than ground truth, and quality claims require real recorded runs.

## Getting started today

1. Read the proposed workflow and choose the first milestone.
2. Decide on providers and local development tools; record those decisions before implementation.
3. Add application code and a reproducible setup guide as the first milestone is built.
4. Use synthetic or public test data and keep credentials outside version control.

**There is no runnable quick start yet.** Installation and run commands will be added when code exists.

## Suggested future layout

```text
apps/mobile/        # Planned Flutter client
services/api/       # Planned application API
evals/              # Planned fixtures and evaluation runs
docs/               # Architecture decisions and demonstration notes
```

These directories describe the intended structure and have not been implemented.

## Portfolio context

This is an independent planned portfolio project, not client work or a production deployment. Its current scope is documentation; update the status and roadmap as working milestones are completed.
