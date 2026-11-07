import copy,json
from pathlib import Path
FIXTURES=Path(__file__).parent/'fixtures'/'promptfoo'
import pytest
from evaldenom.promptfoo import rows_from_summary
from evaldenom.core import InputError,audit,freeze
SOURCE=json.load(open(FIXTURES/'real-local-summary.json'))
def convert(s):return rows_from_summary(s,provider_id='local-fixed-synthetic',prompt_index=0,grader='local-equals-v1')

def test_real_current_harness_result_shapes_not_interpreted_by_error_string():
    result=convert(SOURCE)
    rows=[r for _,r in result['rows']]
    assert [r['metrics']['aggregate']['status'] for r in rows]==['ok','ok','ok','ok','error','error']
    assert [r['trial'] for r in rows]==[1,2,1,2,1,2]
    assert [r['id'] for r in rows]==['easy','easy','hard','hard','broken','broken']
    assert [r['metrics']['aggregate'].get('value') for r in rows]==[1,1,0,0,None,None]


@pytest.mark.parametrize('path,value',[
    (('version',),2),(('version',),True),(('results',),'bad'),
    (('results',0,'provider'),None),(('results',0,'promptIdx'),True),
    (('results',0,'testCase','metadata'),{}),
    (('results',0,'repeatIndex'),None),(('results',0,'repeatIndex'),True),
    (('results',0,'repeatIndex'),-1),
    (('results',0,'vars'),None),(('results',0,'testCase','assert'),[]),
    (('results',0,'failureReason'),3),(('results',0,'failureReason'),False),
    (('results',0,'success'),False),(('results',0,'success'),1),
    (('results',0,'gradingResult'),None),
    (('results',0,'gradingResult','pass'),False),
    (('results',0,'gradingResult','score'),0),
])
def test_unproven_schema_or_identity_is_error(path,value):
    s=copy.deepcopy(SOURCE);target=s
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
    with pytest.raises(InputError):convert(s)


def test_case_and_trial_identity_does_not_follow_testidx_or_order():
    s=copy.deepcopy(SOURCE)
    for i,r in enumerate(s['results']):r['testIdx']=1000-i
    s['results'].reverse()
    rows=convert(s)['rows']
    assert [(r['id'],r['trial']) for _,r in rows]==[('broken',2),('broken',1),('hard',2),('hard',1),('easy',2),('easy',1)]


def test_explicit_selection_reports_every_excluded_row():
    s=copy.deepcopy(SOURCE)
    extras=copy.deepcopy(s['results'])
    for r in extras:r['provider']['id']='other-provider'
    s['results']+=extras
    result=convert(s)
    assert result['source_records']==12
    assert result['excluded_by_explicit_selection']==6
    assert len(result['rows'])==6


def test_nonmatching_explicit_selection_is_not_an_empty_success():
    with pytest.raises(InputError):rows_from_summary(SOURCE,provider_id='missing',prompt_index=0,grader='g')


def test_input_digest_uses_exported_actual_input_and_assertions():
    s=copy.deepcopy(SOURCE)
    before=convert(s)['rows'][0][1]['input_digest']
    s['results'][0]['vars']['question']='changed'
    assert convert(s)['rows'][0][1]['input_digest']!=before
    s=copy.deepcopy(SOURCE)
    s['results'][0]['testCase']['assert'][0]['value']='changed'
    assert convert(s)['rows'][0][1]['input_digest']!=before


def test_converted_rows_do_not_disclose_provider_output_or_error_text():
    serialized=json.dumps(convert(SOURCE))
    assert 'synthetic local provider failure' not in serialized
    assert 'Expected output' not in serialized
    assert 'question' not in serialized

from evaldenom.promptfoo import manifest_from_inline_tests,summary_from_json_export
TESTS=json.load(open(FIXTURES/'prospective-tests.json'))
def plan(tests):return manifest_from_inline_tests(tests,grader='local-equals-v1')


def test_prospective_intention_not_inferred_from_shared_export_subset():
    manifest=plan(TESTS)
    source=copy.deepcopy(SOURCE)
    source['results']=[r for r in source['results'] if r['testCase']['metadata']['external_case_id']!='broken']
    rows=convert(source)['rows']
    result=audit(manifest,{'a':rows,'b':rows})
    assert result['status']=='BLOCKED'
    for run in result['runs'].values():
        assert run['findings']==[{'code':'MISSING_OBSERVATION','id':'broken','trial':1},{'code':'MISSING_OBSERVATION','id':'broken','trial':2}]


def test_prospective_fixture_matches_actual_export_digests():
    manifest=plan(TESTS)
    rows=convert(SOURCE)['rows']
    result=audit(manifest,{'a':rows,'b':rows})
    for run in result['runs'].values():
        assert [f['code'] for f in run['findings']]==['METRIC_ERROR','METRIC_ERROR']


@pytest.mark.parametrize('field,value',[
 ('vars',{'question':['a','b']}),('vars',{'question':{'nested':'value'}}),
 ('vars',{'question':float('nan')}),('vars',{'question':float('inf')}),
 ('options',{}),('options',{'repeat':True}),('options',{'repeat':0}),
 ('options',{'repeat':2,'transform':'x'}),('options',{'repeat':2,'threshold':0.1}),
 ('assert',[]),('assert',[{'type':'javascript','value':'true'}]),
 ('assert',[{'type':'equals','value':'{{expected}}'}]),
 ('assert',[{'type':'equals','value':'file://expected.txt'}]),
 ('assert',[{'type':'equals','value':'OK','weight':2}]),
 ('metadata',{}),('metadata',{'external_case_id':''}),
 ('provider','openai:fake'),('threshold',0.5),('transform','x'),('test','file://x'),
])
def test_prospective_plan_rejects_unresolved_or_unsupported_contract(field,value):
    tests=copy.deepcopy(TESTS);tests[0][field]=value
    with pytest.raises(InputError):plan(tests)


def test_plan_rejects_duplicate_case_ids_instead_of_merging_them():
    tests=copy.deepcopy(TESTS);tests[1]['metadata']['external_case_id']='easy'
    with pytest.raises(InputError):plan(tests)


def test_plan_is_frozen_before_test_mutation():
    tests=copy.deepcopy(TESTS);manifest=plan(tests)
    tests[0]['vars']['question']='later change'
    assert plan(tests)!=manifest
    rows=convert(SOURCE)['rows']
    changed=audit(plan(tests),{'a':rows,'b':rows})
    assert any(f['code']=='INPUT_IDENTITY_MISMATCH' for f in changed['runs']['a']['findings'])


def test_actual_sdk_json_export_wrapper():
    exported=json.load(open(FIXTURES/'real-sdk-export.json'))
    assert len(convert(summary_from_json_export(exported))['rows'])==6
    with pytest.raises(InputError):summary_from_json_export(SOURCE)


@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),None,'1'])
def test_core_blocks_invalid_score_without_adapter_coercion(bad):
    source=copy.deepcopy(SOURCE)
    source['results'][0]['score']=bad
    source['results'][0]['gradingResult']['score']=bad
    try:rows=convert(source)['rows']
    except InputError:return
    result=audit(plan(TESTS),{'a':rows,'b':rows})
    assert any(f['code']=='INVALID_SCORE' for f in result['runs']['a']['findings'])


def actual_pair():
    rows={}
    for label in ['baseline','candidate']:
        exported=json.load(open(FIXTURES/('real-'+label+'-export.json')))
        rows[label]=rows_from_summary(summary_from_json_export(exported),provider_id='local-synthetic-'+label,prompt_index=0,grader='local-equals-v1')['rows']
    return rows


def test_two_separately_executed_local_synthetic_runs_ready():
    result=audit(plan(TESTS),actual_pair())
    assert result['status']=='READY'
    assert all(run['supplied_records']==6 for run in result['runs'].values())


def test_same_hard_case_omitted_from_two_real_exports_blocks():
    rows=actual_pair()
    rows={label:[(line,row) for line,row in run if row['id']!='hard'] for label,run in rows.items()}
    result=audit(plan(TESTS),rows)
    assert result['status']=='BLOCKED'
    for run in result['runs'].values():
        assert run['findings']==[{'code':'MISSING_OBSERVATION','id':'hard','trial':1},{'code':'MISSING_OBSERVATION','id':'hard','trial':2}]


def test_duplicate_trial_in_real_export_not_last_row_wins():
    rows=actual_pair();rows['candidate'].append(rows['candidate'][0])
    result=audit(plan(TESTS),rows)
    assert result['status']=='BLOCKED'
    assert [f['code'] for f in result['runs']['candidate']['findings']]==['DUPLICATE_OBSERVATION']


def test_drift_in_actual_export_even_when_case_and_grade_stay_same():
    exported=json.load(open(FIXTURES/'real-candidate-export.json'))
    exported['results']['results'][0]['testCase']['assert'][0]['value']='different rubric'
    rows=actual_pair()
    rows['candidate']=rows_from_summary(summary_from_json_export(exported),provider_id='local-synthetic-candidate',prompt_index=0,grader='local-equals-v1')['rows']
    result=audit(plan(TESTS),rows)
    assert result['status']=='BLOCKED'
    assert [f['code'] for f in result['runs']['candidate']['findings']]==['INPUT_IDENTITY_MISMATCH']

from evaldenom.promptfoo import audit_promptfoo_exports

def wrapper_pair():
    return {name:json.load(open(FIXTURES/('real-'+name+'-export.json'))) for name in ['baseline','candidate']}

def selections():
    return {name:{'provider_id':'local-synthetic-'+name,'prompt_index':0,'grader':'local-equals-v1'} for name in ['baseline','candidate']}


def test_full_audit_provenance_does_not_claim_whole_export_or_no_selection():
    exports=wrapper_pair()
    extra=copy.deepcopy(exports['baseline']['results']['results'])
    for row in extra:row['provider']['id']='unselected-provider'
    exports['baseline']['results']['results']+=extra
    report=audit_promptfoo_exports(plan(TESTS),exports,selections())
    assert report['status']=='READY'
    assert report['source_adapters']['baseline']['source_records']==12
    assert report['source_adapters']['baseline']['selected_records']==6
    assert report['source_adapters']['baseline']['excluded_by_explicit_selection']==6
    assert not any('No rows are selected' in item for item in report['limitations'])
    text=json.dumps(report)
    assert 'question' not in text
    assert 'contains' not in text
    assert 'output' not in text


@pytest.mark.parametrize('mode',['single','missing','extra','invalid-fields','empty-selection','bad-slice'])
def test_audit_requires_exact_complete_explicit_selection_mapping(mode):
    exports=wrapper_pair();selection=selections()
    if mode=='single':exports.pop('candidate');selection.pop('candidate')
    elif mode=='missing':selection.pop('candidate')
    elif mode=='extra':selection['unknown']=selection['baseline']
    elif mode=='invalid-fields':selection['baseline']['guess']=True
    elif mode=='empty-selection':selection['baseline']={}
    elif mode=='bad-slice':selection['baseline']['provider_id']='not-present'
    with pytest.raises(InputError):audit_promptfoo_exports(plan(TESTS),exports,selection)


def test_wrapper_shared_omission_uses_prospective_plan_not_export_intersection():
    exports=wrapper_pair()
    for value in exports.values():
        value['results']['results']=[row for row in value['results']['results'] if row['testCase']['metadata']['external_case_id']!='hard']
    report=audit_promptfoo_exports(plan(TESTS),exports,selections())
    assert report['status']=='BLOCKED'
    for run in report['runs'].values():
        assert [f['code'] for f in run['findings']]==['MISSING_OBSERVATION','MISSING_OBSERVATION']


def test_wrapper_duplicate_even_identical_never_silently_deduplicated():
    exports=wrapper_pair()
    exports['candidate']['results']['results'].append(copy.deepcopy(exports['candidate']['results']['results'][0]))
    report=audit_promptfoo_exports(plan(TESTS),exports,selections())
    assert report['status']=='BLOCKED'
    assert [f['code'] for f in report['runs']['candidate']['findings']]==['DUPLICATE_OBSERVATION']


def test_wrapper_provider_error_remains_blocked_not_stale_zero():
    exports=wrapper_pair()
    row=exports['candidate']['results']['results'][0]
    row['failureReason']=2;row['success']=False;row['score']=0;row['gradingResult']=None
    report=audit_promptfoo_exports(plan(TESTS),exports,selections())
    assert report['status']=='BLOCKED'
    assert [f['code'] for f in report['runs']['candidate']['findings']]==['METRIC_ERROR']


@pytest.mark.parametrize('repeat',[100001,10**100])
def test_oversized_prospective_repeat_rejected_before_range_materialization(repeat):
    tests=copy.deepcopy(TESTS);tests[0]['options']['repeat']=repeat
    with pytest.raises(InputError,match='at most 100000'):plan(tests)


def test_total_intended_observation_budget_not_just_per_case():
    tests=copy.deepcopy(TESTS)
    for test in tests:test['options']['repeat']=40000
    with pytest.raises(InputError,match='at most 100000'):plan(tests)


def test_prospective_budget_boundary_supported_without_truncating_trials():
    tests=copy.deepcopy(TESTS[:1]);tests[0]['options']['repeat']=100000
    manifest=plan(tests)
    assert manifest['cases'][0]['trials']==list(range(1,100001))

from evaldenom.promptfoo import manifest_from_inline_tests_text,audit_promptfoo_export_texts

def export_texts():
    return {name:(FIXTURES/('real-'+name+'-export.json')).read_text() for name in ['baseline','candidate']}


def test_strict_text_boundary_actual_pair_ready():
    manifest=manifest_from_inline_tests_text((FIXTURES/'prospective-tests.json').read_text(),grader='local-equals-v1')
    assert audit_promptfoo_export_texts(json.dumps(manifest),export_texts(),selections())['status']=='READY'


@pytest.mark.parametrize('payload',[
 '[{"vars":{},"vars":{"x":1}}]',
 '[{"metadata":{"external_case_id":"a","external_case_id":"b"}}]',
 '[{"vars":{"x":NaN}}]',
])
def test_raw_plan_duplicate_or_non_json_constant_rejected(payload):
    with pytest.raises(InputError):manifest_from_inline_tests_text(payload,grader='g')


@pytest.mark.parametrize('replacement',[
 '"score":0,"score":1',
 '"success":false,"success":true',
 '"vars":{"x":0,"x":1}',
 '"repeatIndex":0,"repeatIndex":1',
])
def test_raw_export_duplicate_member_rejected_before_conversion(replacement):
    texts=export_texts()
    texts['candidate']='{"evalId":"synthetic","results":{"version":3,"results":[{'+replacement+'}]}}'
    with pytest.raises(InputError,match='repeated JSON object member'):
        audit_promptfoo_export_texts(json.dumps(plan(TESTS)),texts,selections())


def test_raw_manifest_duplicate_rejected_even_equal_value():
    text=json.dumps(plan(TESTS)).replace('"schema_version": 1','"schema_version":1,"schema_version":1')
    with pytest.raises(InputError,match='repeated JSON object member'):
        audit_promptfoo_export_texts(text,export_texts(),selections())


def test_genuine_default_single_trial_unsupported_without_invented_identity():
    value=json.loads((FIXTURES/'real-single-export.json').read_text())
    assert 'repeatIndex' not in value['results']['results'][0]
    with pytest.raises(InputError,match='repeatIndex'):
        rows_from_summary(summary_from_json_export(value),provider_id='local-single-synthetic',prompt_index=0,grader='g')


def test_genuine_runtime_and_provider_context_mutations_not_persisted_no_attestation():
    value=json.loads((FIXTURES/'real-injected-vars-export.json').read_text())
    rows=value['results']['results']
    assert all(not any(k.startswith('__eval') for k in row['vars']) for row in rows)
    converted=rows_from_summary(summary_from_json_export(value),provider_id='local-injected-vars',prompt_index=0,grader='g')['rows']
    tests=copy.deepcopy(TESTS[:1])
    result=audit(manifest_from_inline_tests(tests,grader='g'),{'a':converted,'b':converted})
    # Harness exports omit runtime identifiers and provider context mutation.
    # READY binds only exported vars, never provider-executed bytes/context.
    assert result['status']=='READY'
    assert all(row['vars']=={'question':'easy'} for row in rows)


def test_genuine_explicit_repeat_one_also_unsupported_missing_trial_identity():
    value=json.loads((FIXTURES/'real-repeat-one-export.json').read_text())
    assert 'repeatIndex' not in value['results']['results'][0]
    with pytest.raises(InputError,match='repeatIndex'):
        rows_from_summary(summary_from_json_export(value),provider_id='local-single-synthetic',prompt_index=0,grader='g')


def test_prospective_repeat_one_rejected_early_to_match_actual_export_limit():
    tests=copy.deepcopy(TESTS);tests[0]['options']['repeat']=1
    with pytest.raises(InputError,match='repeat at least 2'):plan(tests)
