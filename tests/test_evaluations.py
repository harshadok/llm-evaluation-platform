import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.runtime import ProviderError

DATA = json.loads((Path(__file__).resolve().parents[1] / 'examples/dataset.json').read_text())


def dataset(client):
    response = client.post('/datasets', json=DATA)
    assert response.status_code == 201
    return response.json()


def test_fixture_run_export_and_versions(tmp_path):
    client = TestClient(create_app(tmp_path / 'db'))
    source = dataset(client)
    assert dataset(client)['id'] == source['id']
    run = client.post('/runs', json={'dataset_id': source['id'], 'provider': 'fixture'}).json()
    assert run['metrics']['mean_score'] == 1
    assert run['metrics']['cost'] is None
    assert all(item['input_tokens'] is None for item in run['results'])
    assert client.get('/runs/' + run['id'] + '/traces').json()[-1]['event'] == 'run_completed'
    assert 'arithmetic' in client.get('/runs/' + run['id'] + '/export?format=csv').text
    changed = dict(DATA, cases=[dict(DATA['cases'][0], expected='5')])
    second = client.post('/datasets', json=changed).json()
    assert second['version'] == 2
    assert client.get('/datasets/' + source['id']).json()['cases'][0]['expected'] == '4'
    other = client.post('/runs', json={'dataset_id': second['id'], 'provider': 'fixture'}).json()
    assert client.post('/comparisons', json={'baseline_id': run['id'], 'candidate_id': other['id']}).status_code == 422


def test_provider_failures_count_as_zero_and_trigger_regression(tmp_path):
    class Broken:
        def complete(self, *args, **kwargs):
            raise ProviderError('offline')
    client = TestClient(create_app(tmp_path / 'db', lambda model: Broken()))
    source = dataset(client)
    baseline = client.post('/runs', json={'dataset_id': source['id'], 'provider': 'fixture'}).json()
    failed = client.post('/runs', json={'dataset_id': source['id'], 'provider': 'ollama'}).json()
    assert failed['status'] == 'completed'
    assert failed['metrics']['mean_score'] == 0
    assert failed['metrics']['error_count'] == 3
    comparison = client.post('/comparisons', json={'baseline_id': baseline['id'], 'candidate_id': failed['id']}).json()
    assert comparison['passed'] is False
    assert len(comparison['regressed_cases']) == 3


def test_deterministic_tool_call_scoring_and_invalid_schema(tmp_path):
    client = TestClient(create_app(tmp_path / 'db'))
    source = client.post('/datasets', json={'name': 'tools', 'cases': [{'id': 'a', 'input': 'get slots', 'expected': '{"name":"slots","arguments":{"day":"Monday"}}', 'scorer': 'tool_call', 'fixture_output': '{"arguments":{"day":"Monday"},"name":"slots"}'}]}).json()
    result = client.post('/runs', json={'dataset_id': source['id'], 'provider': 'fixture'}).json()
    assert result['metrics']['mean_score'] == 1
    invalid = {'name': 'unsafe-schema', 'cases': [{'id':'x','input':'x','expected':'','scorer':'json_schema','output_schema':{'$ref':'http://localhost/private'}}]}
    assert client.post('/datasets', json=invalid).status_code == 422
    invalid['cases'][0]['output_schema'] = {'type': 'invalid-type'}
    assert client.post('/datasets', json=invalid).status_code == 422
    assert client.post('/runs', json={'dataset_id': 'missing'}).status_code == 404


def test_provider_tokens_and_persistence(tmp_path):
    class Model:
        def complete(self, *args, **kwargs):
            return {'text': '4', 'input_tokens': 10, 'output_tokens': 1}
    client = TestClient(create_app(tmp_path / 'db', lambda model: Model()))
    source = dataset(client)
    result = client.post('/runs', json={'dataset_id': source['id']}).json()
    assert result['results'][0]['input_tokens'] == 10
    assert TestClient(create_app(tmp_path / 'db')).get('/runs/' + result['id']).json()['status'] == 'completed'
