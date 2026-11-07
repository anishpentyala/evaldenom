import json
from pathlib import Path
from evaldenom import audit, freeze
from evaldenom.core import read_json,read_jsonl
ROOT=Path(__file__).resolve().parents[1]/'examples'


def test_committed_manifest_rebuilds_and_examples_show_denominator_failure():
    m=freeze(read_jsonl(ROOT/'cases.jsonl'),read_json(ROOT/'metrics.json'))
    assert m==read_json(ROOT/'manifest.json')
    base=read_jsonl(ROOT/'baseline.jsonl')
    assert audit(m,{'base':base,'candidate':read_jsonl(ROOT/'candidate-complete.jsonl')})['status']=='READY'
    result=audit(m,{'base':base,'candidate':read_jsonl(ROOT/'candidate-missing.jsonl')})
    assert result['status']=='BLOCKED'
    findings=result['runs']['candidate']['findings']
    assert findings==[{'code':'MISSING_OBSERVATION','id':'hard','trial':1},
                      {'code':'MISSING_OBSERVATION','id':'hard','trial':2}]
