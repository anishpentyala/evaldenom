"""Exercise the actual public CLI, including strict parsing and output safety."""
import json
from pathlib import Path
import pytest
from evaldenom.cli import main
from evaldenom.promptfoo import manifest_from_inline_tests

FIXTURES=Path(__file__).parent/'fixtures'/'promptfoo'

def setup_files(tmp_path):
    tests=tmp_path/'tests.json'
    tests.write_bytes((FIXTURES/'prospective-tests.json').read_bytes())
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(manifest_from_inline_tests(json.loads(tests.read_text()),grader='local-equals-v1')))
    exports=[]
    for label in ('baseline','candidate'):
        path=tmp_path/(label+'.json')
        path.write_bytes((FIXTURES/('real-'+label+'-export.json')).read_bytes())
        exports.append(path)
    selections=tmp_path/'selections.json'
    selections.write_text(json.dumps({label:{'provider_id':'local-synthetic-'+label,'prompt_index':0,'grader':'local-equals-v1'} for label in ('baseline','candidate')}))
    return [tests,manifest,*exports,selections]

def audit_args(paths):
    _,m,a,b,s=paths
    return ['promptfoo-audit',str(m),'--run','baseline='+str(a),'--run','candidate='+str(b),'--selections',str(s)]

def test_ready_actual_pair_stdout_and_freeze(tmp_path,capsys):
    paths=setup_files(tmp_path);target=tmp_path/'frozen.json'
    assert main(['promptfoo-freeze',str(paths[0]),'--grader','local-equals-v1','--output',str(target)])==0
    assert json.loads(target.read_text())==json.loads(paths[1].read_text())
    assert main(audit_args(paths))==0
    report=json.loads(capsys.readouterr().out)
    assert report['status']=='READY'
    assert report['source_adapters']['baseline']['selected_records']==6
    assert not list(tmp_path.glob('.evaldenom-*'))

def test_shared_omission_is_blocked_not_empty_success(tmp_path,capsys):
    paths=setup_files(tmp_path)
    for path in paths[2:4]:
        data=json.loads(path.read_text());data['results']['results']=[r for r in data['results']['results'] if r['testCase']['metadata']['external_case_id']!='hard'];path.write_text(json.dumps(data))
    assert main(audit_args(paths))==1
    report=json.loads(capsys.readouterr().out)
    for run in report['runs'].values():
        assert run['findings']==[{'code':'MISSING_OBSERVATION','id':'hard','trial':1},{'code':'MISSING_OBSERVATION','id':'hard','trial':2}]

@pytest.mark.parametrize('index',[1,2,3,4])
@pytest.mark.parametrize('bad',['{"PRIVATE-CANARY":1,"PRIVATE-CANARY":2}','NaN','{','[]'])
def test_untrusted_files_fail_without_clobber_or_echo(tmp_path,capsys,index,bad):
    paths=setup_files(tmp_path);paths[index].write_text(bad)
    output=tmp_path/'result.json';output.write_text('KEEP')
    with pytest.raises(SystemExit) as error:main(audit_args(paths)+['--output',str(output)])
    assert error.value.code==2 and output.read_text()=='KEEP'
    captured=capsys.readouterr();assert captured.out=='' and 'PRIVATE-CANARY' not in captured.err
    assert not list(tmp_path.glob('.evaldenom-*'))

@pytest.mark.parametrize('index',[1,2,3,4])
@pytest.mark.parametrize('symlink',[False,True])
def test_output_cannot_replace_any_source(tmp_path,index,symlink):
    paths=setup_files(tmp_path);target=paths[index];before=target.read_bytes()
    if symlink:
        alias=tmp_path/'alias.json';alias.symlink_to(target);target=alias
    with pytest.raises(SystemExit) as error:main(audit_args(paths)+['--output',str(target)])
    assert error.value.code==2 and target.read_bytes()==before

@pytest.mark.parametrize('bad',['{"PRIVATE-CANARY":1,"PRIVATE-CANARY":2}','NaN','[]','[{}]','{'])
def test_freeze_strict_boundary(tmp_path,capsys,bad):
    source=tmp_path/'tests.json';source.write_text(bad)
    output=tmp_path/'manifest.json';output.write_text('KEEP')
    with pytest.raises(SystemExit) as error:main(['promptfoo-freeze',str(source),'--grader','g','--output',str(output)])
    assert error.value.code==2 and output.read_text()=='KEEP'
    captured=capsys.readouterr();assert not captured.out and 'PRIVATE-CANARY' not in captured.err

def test_freeze_output_cannot_replace_tests(tmp_path):
    paths=setup_files(tmp_path);before=paths[0].read_bytes()
    with pytest.raises(SystemExit) as error:main(['promptfoo-freeze',str(paths[0]),'--grader','g','--output',str(paths[0])])
    assert error.value.code==2 and paths[0].read_bytes()==before

@pytest.mark.parametrize('entry',['baseline=other','missing-equals','=path','name='])
def test_invalid_or_duplicate_routes(tmp_path,entry):
    paths=setup_files(tmp_path)
    with pytest.raises(SystemExit) as error:main(audit_args(paths)+['--run',entry])
    assert error.value.code==2

def test_equals_in_source_path_is_preserved(tmp_path,capsys):
    paths=setup_files(tmp_path);target=tmp_path/'candidate=fixture.json';paths[3].rename(target);paths[3]=target
    assert main(audit_args(paths))==0
    assert json.loads(capsys.readouterr().out)['status']=='READY'

def test_missing_source_does_not_publish_verdict(tmp_path,capsys):
    paths=setup_files(tmp_path);paths[4].unlink()
    with pytest.raises(SystemExit) as error:main(audit_args(paths))
    assert error.value.code==2 and not capsys.readouterr().out

def test_wrong_selection_cannot_be_inferred(tmp_path,capsys):
    paths=setup_files(tmp_path);data=json.loads(paths[4].read_text());data['candidate']['provider_id']='wrong';paths[4].write_text(json.dumps(data))
    with pytest.raises(SystemExit) as error:main(audit_args(paths))
    assert error.value.code==2 and not capsys.readouterr().out

@pytest.mark.parametrize('index',[1,2,3,4])
def test_duplicate_member_in_otherwise_valid_input_is_rejected(tmp_path,index,capsys):
    paths=setup_files(tmp_path);data=json.loads(paths[index].read_text());key=next(iter(data));text=json.dumps(data)
    paths[index].write_text(text[:-1]+','+json.dumps(key)+':'+json.dumps(data[key])+'}')
    with pytest.raises(SystemExit) as error:main(audit_args(paths))
    assert error.value.code==2 and not capsys.readouterr().out

def test_duplicate_member_in_otherwise_valid_tests_is_rejected(tmp_path):
    paths=setup_files(tmp_path);text=json.dumps(json.loads(paths[0].read_text())).replace('"external_case_id": "easy"','"external_case_id": "easy", "external_case_id": "easy"')
    assert text!=paths[0].read_text();paths[0].write_text(text)
    with pytest.raises(SystemExit) as error:main(['promptfoo-freeze',str(paths[0]),'--grader','g','--output',str(tmp_path/'manifest2.json')])
    assert error.value.code==2

@pytest.mark.parametrize('constant',['NaN','Infinity','-Infinity'])
def test_nonjson_constant_even_in_ignored_export_field_is_rejected(tmp_path,capsys,constant):
    paths=setup_files(tmp_path);text=paths[2].read_text();paths[2].write_text(text[:-2]+',"ignored_probe":'+constant+'}\n')
    # A permissive parser would accept it, and the adapter does not bind this field.
    from evaldenom.promptfoo import audit_promptfoo_exports
    assert audit_promptfoo_exports(json.loads(paths[1].read_text()),{name:json.loads(path.read_text()) for name,path in zip(('baseline','candidate'),paths[2:4])},json.loads(paths[4].read_text()))['status']=='READY'
    with pytest.raises(SystemExit) as error:main(audit_args(paths))
    assert error.value.code==2 and not capsys.readouterr().out

@pytest.mark.parametrize('label,index,bad',[
    ('candidate',0,True),('baseline',2,False),('candidate',0,'1'),
    ('baseline',2,'0'),('candidate',0,None),
])
def test_aggregate_score_type_error_does_not_publish_ready_or_replace_report(tmp_path,capsys,label,index,bad):
    paths=setup_files(tmp_path);path=paths[2 if label=='baseline' else 3]
    data=json.loads(path.read_text());data['results']['results'][index]['gradingResult']['score']=bad
    path.write_text(json.dumps(data));output=tmp_path/'report.json';output.write_text('KEEP')
    with pytest.raises(SystemExit) as error:main(audit_args(paths)+['--output',str(output)])
    assert error.value.code==2 and output.read_text()=='KEEP'
    assert capsys.readouterr().out=='' and not list(tmp_path.glob('.evaldenom-*'))
