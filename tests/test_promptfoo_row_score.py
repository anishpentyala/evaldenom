"""The row score needs its own numeric check before equality with grading score.

Python bool/int equality is not evidence that both JSON fields are numeric.
The core audit already blocks the leaked boolean; this is adapter validation,
not a false READY fix.
"""
import copy
import json
from pathlib import Path

import pytest
from evaldenom.core import InputError, audit, freeze
from evaldenom.promptfoo import rows_from_summary

SOURCE = json.loads((Path(__file__).parent/'fixtures/promptfoo/real-local-summary.json').read_text())


def convert(source):
    return rows_from_summary(source,provider_id='local-fixed-synthetic',prompt_index=0,grader='local-equals-v1')


def change_score(value,grading=1):
    source=copy.deepcopy(SOURCE)
    row=source['results'][0]
    row['score']=value
    row['gradingResult']['score']=grading
    row['success']=bool(grading)
    row['failureReason']=0 if grading else 1
    row['gradingResult']['pass']=bool(grading)
    return source


@pytest.mark.parametrize('value,grading',[(True,1),(False,0)])
def test_boolean_row_score_cannot_alias_numeric_grading_score(value,grading):
    with pytest.raises(InputError,match='grading evidence'):
        convert(change_score(value,grading))


@pytest.mark.parametrize('value',[None,'1',[],{},float('inf'),float('nan')])
def test_nonnumeric_or_nonfinite_row_score_is_unusable(value):
    with pytest.raises(InputError):
        convert(change_score(value))


@pytest.mark.parametrize('value,grading',[(1,1.0),(1.0,1),(0,0.0),(0.0,0)])
def test_equivalent_finite_numeric_row_scores_are_preserved(value,grading):
    row=convert(change_score(value,grading))['rows'][0][1]
    assert type(row['metrics']['aggregate']['value']) is type(value)
    assert row['metrics']['aggregate']['value']==value


def test_provider_error_does_not_trust_even_a_boolean_stale_score():
    source=change_score(True)
    row=source['results'][0]
    row['failureReason']=2
    row['success']=False
    row.pop('gradingResult')
    metric=convert(source)['rows'][0][1]['metrics']['aggregate']
    assert metric==dict(status='error',grader='local-equals-v1',direction='higher')


def test_unchanged_core_defense_refuses_boolean_scores_even_if_adapter_leaks():
    source=SOURCE['results'][0]
    manifest=freeze([(1,dict(id='easy',input={'vars':source['vars'],'assert':source['testCase']['assert']},trials=[1]))],
                    [dict(name='aggregate',grader='local-equals-v1',direction='higher',min=0,max=1)])
    from evaldenom.core import input_digest
    row=dict(id='easy',trial=1,input_digest=manifest['cases'][0]['input_digest'],
             metrics={'aggregate':dict(status='ok',grader='local-equals-v1',direction='higher',value=True)})
    report=audit(manifest,dict(baseline=[(1,row)],candidate=[(1,row)]))
    assert report['status']=='BLOCKED'
    assert [x['code']for x in report['runs']['candidate']['findings']]==['INVALID_SCORE']


@pytest.mark.parametrize('value,grading',[(True,1),(False,0)])
def test_cli_input_error_does_not_publish_or_echo_scores(tmp_path,capsys,value,grading):
    from evaldenom.cli import main
    from evaldenom.promptfoo import manifest_from_inline_tests
    fixtures=Path(__file__).parent/'fixtures/promptfoo'
    tests=json.loads((fixtures/'prospective-tests.json').read_text())
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(manifest_from_inline_tests(tests,grader='local-equals-v1')))
    selections=tmp_path/'selections.json'
    selections.write_text(json.dumps({name:dict(provider_id='local-synthetic-'+name,prompt_index=0,grader='local-equals-v1')for name in ['baseline','candidate']}))
    paths=[]
    for name in ['baseline','candidate']:
        data=json.loads((fixtures/('real-'+name+'-export.json')).read_text())
        if name=='candidate':
            r=data['results']['results'][0]
            r.update(score=value,success=bool(grading),failureReason=0 if grading else 1)
            r['gradingResult'].update(score=grading,**{'pass':bool(grading)})
        path=tmp_path/(name+'.json');path.write_text(json.dumps(data));paths.append(path)
    output=tmp_path/'report.json';output.write_text('KEEP')
    with pytest.raises(SystemExit)as error:
        main(['promptfoo-audit',str(manifest),'--run','baseline='+str(paths[0]),
              '--run','candidate='+str(paths[1]),'--selections',str(selections),'--output',str(output)])
    assert error.value.code==2
    assert output.read_text()=='KEEP'
    assert capsys.readouterr().out==''
