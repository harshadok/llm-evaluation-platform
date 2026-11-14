import csv
import hashlib
import io
import json
import os
import time
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .runtime import LocalLLM, ProviderError, Store, now


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=100)
    input: str = Field(min_length=1, max_length=8000)
    expected: str = Field(max_length=8000)
    scorer: Literal['exact', 'contains', 'json_schema', 'tool_call'] = 'exact'
    output_schema: Optional[Dict[str, Any]] = None
    fixture_output: Optional[str] = Field(default=None, max_length=16000)

    @model_validator(mode='after')
    def valid_reference(self):
        if self.scorer == 'json_schema':
            if self.output_schema is None:
                raise ValueError('json_schema scoring requires output_schema.')
            # Remote references could make scoring perform unintended network requests.
            encoded = json.dumps(self.output_schema)
            if '"$ref"' in encoded or '"$dynamicRef"' in encoded:
                raise ValueError('Schema references are not supported.')
            try:
                Draft202012Validator.check_schema(self.output_schema)
            except SchemaError as exc:
                raise ValueError('Invalid JSON Schema.') from exc
        if self.scorer == 'tool_call':
            try:
                target = json.loads(self.expected)
                if not isinstance(target.get('name'), str) or not isinstance(target.get('arguments'), dict):
                    raise ValueError('Expected a tool name and arguments object.')
            except (ValueError, AttributeError) as exc:
                raise ValueError('tool_call expected must be JSON with name and arguments.') from exc
        if self.scorer == 'contains' and not self.expected.strip():
            raise ValueError('contains reference must not be blank.')
        return self


class Dataset(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cases: List[Case] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError('Case IDs must be unique.')
        return self


class RunRequest(BaseModel):
    dataset_id: str
    provider: Literal['ollama', 'fixture'] = 'ollama'
    prompt: str = Field(default='Answer the following concisely.\n{input}', max_length=4000)
    model: Optional[str] = Field(default=None, max_length=100)
    max_tokens: int = Field(default=128, ge=1, le=1024)


class Comparison(BaseModel):
    baseline_id: str
    candidate_id: str
    max_score_drop: float = Field(default=0, ge=0, le=1)
    max_latency_increase_ms: Optional[float] = Field(default=None, ge=0)


def score(case, output):
    if case.scorer == 'exact':
        return float(output.strip() == case.expected.strip())
    if case.scorer == 'contains':
        return float(case.expected.casefold() in output.casefold())
    try:
        value = json.loads(output)
        if case.scorer == 'json_schema':
            return float(Draft202012Validator(case.output_schema).is_valid(value))
        expected = json.loads(case.expected)
        return float(isinstance(value, dict) and value.get('name') == expected['name'] and value.get('arguments') == expected['arguments'])
    except (ValueError, TypeError):
        return 0.0


def create_app(database=None, model_factory=None):
    app = FastAPI(title='LLM Evaluation Platform', version='1.0.0', description='Versioned datasets, repeatable local-model runs, deterministic scoring, traces, regression comparison, and exports.')
    store = Store(database or os.environ.get('DATABASE_PATH', 'data/evaluations.sqlite3'))
    factory = model_factory or (lambda model: LocalLLM(model=model))
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL, digest TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, UNIQUE(name,version))')

    def dataset(record_id):
        with store.connect() as db:
            row = db.execute('SELECT * FROM datasets WHERE id=?', (record_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Dataset not found.')
        return dict(json.loads(row['payload']), id=row['id'], version=row['version'], digest=row['digest'])

    def read_run(record_id):
        result = store.get('run', record_id)
        if result is None:
            raise HTTPException(404, 'Run not found.')
        return dict(result, id=record_id)

    @app.get('/', include_in_schema=False)
    def index():
        from fastapi.responses import RedirectResponse
        return RedirectResponse('/docs')

    @app.get('/health')
    def health():
        return {'status': 'ready', 'default_model': os.environ.get('AI_MODEL', 'qwen2.5:1.5b')}

    @app.post('/datasets', status_code=201)
    def add_dataset(body: Dataset):
        payload = json.dumps(body.model_dump(), sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id FROM datasets WHERE digest=?', (digest,)).fetchone()
            if existing:
                record_id = existing[0]
            else:
                version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM datasets WHERE name=?', (body.name,)).fetchone()[0]
                record_id = digest[:24]
                db.execute('INSERT INTO datasets VALUES (?,?,?,?,?)', (record_id, body.name, version, digest, payload))
        return dataset(record_id)

    @app.get('/datasets')
    def datasets():
        with store.connect() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM datasets ORDER BY rowid DESC LIMIT 100')]
        return [dataset(record_id) for record_id in ids]

    @app.get('/datasets/{record_id}')
    def get_dataset(record_id: str):
        return dataset(record_id)

    @app.post('/runs', status_code=201)
    def run(body: RunRequest):
        source = dataset(body.dataset_id)
        cases = [Case.model_validate(case) for case in source['cases']]
        if body.provider == 'fixture' and any(case.fixture_output is None for case in cases):
            raise HTTPException(422, 'Every case needs fixture_output for a fixture run.')
        config = body.model_dump()
        config['model'] = body.model or os.environ.get('AI_MODEL', 'qwen2.5:1.5b')
        record = {'created_at': now(), 'status': 'running', 'config': config, 'dataset_digest': source['digest'], 'dataset_version': source['version'], 'results': [], 'traces': []}
        record_id = store.put('run', record)
        def trace(event, **fields):
            record['traces'].append(dict(timestamp=now(), event=event, **fields))
        trace('run_started', case_count=len(cases))
        model = factory(config['model']) if body.provider == 'ollama' else None
        for case in cases:
            started = time.perf_counter()
            trace('case_started', case_id=case.id)
            result = {'case_id': case.id, 'input': case.input, 'scorer': case.scorer, 'score': 0.0,
                      'input_tokens': None, 'output_tokens': None, 'cost': None, 'error': None}
            try:
                if body.provider == 'fixture':
                    output = case.fixture_output
                else:
                    reply = model.complete([{'role': 'user', 'content': body.prompt.replace('{input}', case.input)}], max_tokens=body.max_tokens)
                    output = reply['text']
                    result.update(input_tokens=reply.get('input_tokens'), output_tokens=reply.get('output_tokens'))
                result.update(output=output, score=score(case, output))
            except (ProviderError, ValueError, TypeError, KeyError) as exc:
                result.update(output=None, error=type(exc).__name__)
            result['latency_ms'] = round((time.perf_counter() - started) * 1000, 3)
            record['results'].append(result)
            trace('case_failed' if result['error'] else 'case_completed', case_id=case.id, score=result['score'], latency_ms=result['latency_ms'])
            store.put('run', record, record_id)
        record['metrics'] = {'mean_score': sum(item['score'] for item in record['results']) / len(cases),
                             'error_count': sum(item['error'] is not None for item in record['results']),
                             'case_count': len(cases),
                             'mean_latency_ms': sum(item['latency_ms'] for item in record['results']) / len(cases),
                             'cost': None}
        record.update(status='completed', completed_at=now())
        trace('run_completed', **record['metrics'])
        store.put('run', record, record_id)
        return dict(record, id=record_id)

    @app.get('/runs')
    def runs():
        return store.list('run')

    @app.get('/runs/{record_id}')
    def get_run(record_id: str):
        return read_run(record_id)

    @app.get('/runs/{record_id}/traces')
    def traces(record_id: str):
        return read_run(record_id)['traces']

    @app.post('/comparisons')
    def compare(body: Comparison):
        baseline, candidate = read_run(body.baseline_id), read_run(body.candidate_id)
        if baseline['status'] != 'completed' or candidate['status'] != 'completed':
            raise HTTPException(409, 'Both runs must be completed.')
        if baseline['dataset_digest'] != candidate['dataset_digest']:
            raise HTTPException(422, 'Comparisons require the same immutable dataset version.')
        before = {item['case_id']: item for item in baseline['results']}
        after = {item['case_id']: item for item in candidate['results']}
        lost = [key for key in before if after[key]['score'] < before[key]['score']]
        drop = baseline['metrics']['mean_score'] - candidate['metrics']['mean_score']
        more_errors = candidate['metrics']['error_count'] > baseline['metrics']['error_count']
        latency_delta = candidate['metrics']['mean_latency_ms'] - baseline['metrics']['mean_latency_ms']
        latency_failure = body.max_latency_increase_ms is not None and latency_delta > body.max_latency_increase_ms
        result = {'baseline_id': body.baseline_id, 'candidate_id': body.candidate_id, 'score_drop': drop,
                  'regressed_cases': lost, 'more_errors': more_errors, 'latency_delta_ms': latency_delta,
                  'passed': drop <= body.max_score_drop and not more_errors and not latency_failure,
                  'thresholds': body.model_dump(), 'created_at': now()}
        record_id = store.put('comparison', result)
        return dict(result, id=record_id)

    @app.get('/runs/{record_id}/export')
    def export(record_id: str, format: str = 'json'):
        record = read_run(record_id)
        if format == 'json':
            return Response(json.dumps(record, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="evaluation.json"'})
        if format != 'csv':
            raise HTTPException(422, 'Use format=json or csv.')
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['case_id', 'score', 'latency_ms', 'input_tokens', 'output_tokens', 'error'])
        for item in record['results']:
            case_id = item['case_id']
            if case_id.startswith(('=', '+', '-', '@', '\t', '\r')):
                case_id = "'" + case_id
            writer.writerow([case_id, item['score'], item['latency_ms'], item['input_tokens'], item['output_tokens'], item['error']])
        return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="evaluation.csv"'})

    return app


app = create_app()
