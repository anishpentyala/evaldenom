"""Metamorphic and seeded corruption controls over intended identities."""
import copy
import random
import pytest
from evaldenom import audit, freeze
from evaldenom.core import InputError
from test_contract import setup


def test_seeded_export_corruptions_cannot_pass_coverage():
    rng = random.Random(20261106)
    metric = [{'name':'m','grader':'v1','direction':'higher'}]
    cases = [(i+1, {'id':'case-%03d'%i,'input':{'x':i},'trials':[1,2,3]}) for i in range(30)]
    m = freeze(cases, metric)
    rows = [(i+1, {'id':c['id'],'trial':t,'input_digest':c['input_digest'],
                   'metrics':{'m':{'status':'ok','grader':'v1','direction':'higher','value':1}}})
            for i,(c,t) in enumerate((c,t) for c in m['cases'] for t in c['trials'])]
    for _ in range(100):
        candidate = copy.deepcopy(rows)
        rng.shuffle(candidate)
        assert audit(m, {'a':rows,'b':candidate})['status'] == 'READY'
        j = rng.randrange(len(candidate))
        mode = rng.choice(['drop','duplicate','unknown','trial','input','metric'])
        if mode=='drop':candidate.pop(j)
        elif mode=='duplicate':candidate.append(copy.deepcopy(candidate[j]))
        elif mode=='unknown':candidate[j][1]['id']='not-intended'
        elif mode=='trial':candidate[j][1]['trial']=999
        elif mode=='input':candidate[j][1]['input_digest']='pyjson-v1:'+'0'*64
        else:candidate[j][1]['metrics'].clear()
        assert audit(m, {'a':rows,'b':candidate})['status']=='BLOCKED',mode


@pytest.mark.parametrize('metric_field,value', [
    ('min', True), ('min','0'), ('max',float('inf')), ('direction','up'),
    ('grader',''), ('name','')])
def test_malformed_metric_contract_is_error_not_partial_policy(metric_field,value):
    spec={'name':'m','grader':'v1','direction':'higher'}
    spec[metric_field]=value
    with pytest.raises(InputError):
        freeze([(1,{'id':'a','input':{},'trials':[1]})],[spec])


@pytest.mark.parametrize('mutation', ['extra','empty','boolversion','duplicate-trial','missing-grader'])
def test_malformed_manifests_never_certify(mutation):
    m,rows=setup()
    if mutation=='extra':m['guessed_policy']='skip errors'
    if mutation=='empty':m['metrics']=[]
    if mutation=='boolversion':m['schema_version']=True
    if mutation=='duplicate-trial':m['cases'][0]['trials']=[1,1]
    if mutation=='missing-grader':del m['metrics'][0]['grader']
    with pytest.raises(InputError):audit(m,{'a':rows,'b':rows})


def test_both_runs_missing_same_case_still_blocked_against_manifest():
    m,rows=setup()
    # Comparing only the intersection would see no coverage difference.
    rows=rows[:-1]
    result=audit(m,{'a':rows,'b':rows})
    assert result['status']=='BLOCKED'
    assert all(any(f['code']=='MISSING_OBSERVATION' for f in r['findings'])
               for r in result['runs'].values())


def test_nonmatching_scores_are_not_a_contract_regression():
    m,rows=setup()
    b=copy.deepcopy(rows)
    for _,row in b:row['metrics']['quality']['value']=0
    assert audit(m,{'a':rows,'b':b})['status']=='READY'


def test_manifest_digest_records_declared_grader_and_intended_trials():
    m,rows=setup()
    first=audit(m,{'a':rows,'b':rows})['manifest_digest']
    m['metrics'][0]['grader']='v2'
    assert audit(m,{'a':rows,'b':rows})['manifest_digest']!=first


def test_same_run_file_under_two_names_is_not_claimed_independent():
    m,rows=setup()
    result=audit(m,{'a':rows,'b':rows})
    assert result['status']=='READY'
    assert any('statistically' in text for text in result['limitations'])
