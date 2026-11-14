"""Run a synthetic-data walkthrough against a running local API."""
import argparse
import json
from pathlib import Path
import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8104')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
client = httpx.Client(base_url=args.url, timeout=300)

def call(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()

dataset = call('POST','/datasets',json=json.loads((root/'examples/dataset.json').read_text()))
baseline = call('POST','/runs',json={'dataset_id':dataset['id'],'provider':'fixture'})
candidate = call('POST','/runs',json={'dataset_id':dataset['id'],'provider':'ollama'})
comparison = call('POST','/comparisons',json={'baseline_id':baseline['id'],'candidate_id':candidate['id']})
print(json.dumps({'fixture_baseline':baseline['metrics'],'real_model':candidate['metrics'],'comparison':comparison},indent=2))
