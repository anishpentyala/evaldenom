"""Prospective drift is separate from scoring or export readiness."""
import copy
import json

import pytest

from evaldenom.core import InputError
from evaldenom.manifestdiff import compare_manifests
from evaldenom.cli import main
from test_contract import setup


def test_identical_contract_matches_without_mutation():
    previous, _ = setup()
    current = copy.deepcopy(previous)
    current['cases'].reverse()
    current['cases'][1]['trials'].reverse()
    before = copy.deepcopy((previous, current))
    report = compare_manifests(previous, current)
    assert report['status'] == 'MATCH' and report['changes'] == []
    assert report['previous'] == report['current'] == {'cases': 2, 'observations': 3, 'metrics': 1}
    assert report['source_manifest_digests']['previous'] != report['source_manifest_digests']['current']
    assert (previous, current) == before
    assert report['kind'] == 'evaldenom.manifest-comparison'


@pytest.mark.parametrize('field,value,code', [
    ('input_digest', 'pyjson-v1:' + '0' * 64, 'INPUT_IDENTITY_CHANGED'),
    ('cluster', 'new-group', 'CLUSTER_CHANGED'),
    ('trials', [1], 'TRIAL_REMOVED'), ('trials', [1, 2, 5], 'TRIAL_ADDED'),
])
def test_same_id_cannot_hide_contract_drift(field, value, code):
    previous, _ = setup()
    current = copy.deepcopy(previous)
    current['cases'][0][field] = value
    report = compare_manifests(previous, current)
    assert report['status'] == 'CHANGED'
    assert report['changes'][0]['code'] == code
    assert report['changes'][0]['id'] == 'a'


@pytest.mark.parametrize('field,value,code', [
    ('grader', 'rubric-v2', 'GRADER_CHANGED'), ('direction', 'lower', 'DIRECTION_CHANGED'),
    ('min', -1, 'MINIMUM_CHANGED'), ('max', 2, 'MAXIMUM_CHANGED'),
])
def test_metric_changes_named_without_copying_rubric_values(field, value, code):
    previous, _ = setup()
    current = copy.deepcopy(previous)
    current['metrics'][0][field] = value
    report = compare_manifests(previous, current)
    assert report['changes'] == [{'code': code, 'metric': 'quality'}]
    assert 'rubric-v2' not in json.dumps(report)


def test_absent_bound_and_absent_cluster_are_not_explicit_values():
    previous, _ = setup()
    current = copy.deepcopy(previous)
    del current['metrics'][0]['min']
    del current['cases'][0]['cluster']
    assert compare_manifests(previous, current)['changes'] == [
        {'code': 'CLUSTER_CHANGED', 'id': 'a'}, {'code': 'MINIMUM_CHANGED', 'metric': 'quality'}]


def test_equivalent_numeric_bound_spellings_match_core_audit_semantics():
    previous, _ = setup()
    current = copy.deepcopy(previous)
    current['metrics'][0].update(min=0.0, max=1.0)
    assert compare_manifests(previous, current)['status'] == 'MATCH'


def test_additions_removals_do_not_align_by_position():
    previous, _ = setup()
    current = copy.deepcopy(previous)
    current['cases'][0]['id'] = 'c'
    current['metrics'][0]['name'] = 'precision'
    assert compare_manifests(previous, current)['changes'] == [
        {'code': 'CASE_REMOVED', 'id': 'a'}, {'code': 'CASE_ADDED', 'id': 'c'},
        {'code': 'METRIC_ADDED', 'metric': 'precision'}, {'code': 'METRIC_REMOVED', 'metric': 'quality'}]


@pytest.mark.parametrize('side', ['previous', 'current'])
@pytest.mark.parametrize('malform', ['duplicate_case', 'duplicate_metric', 'trial_bool', 'bad_digest', 'schema_bool'])
def test_both_complete_inputs_validated_before_a_verdict(side, malform):
    manifest, _ = setup()
    bad = copy.deepcopy(manifest)
    if malform == 'duplicate_case': bad['cases'].append(copy.deepcopy(bad['cases'][0]))
    if malform == 'duplicate_metric': bad['metrics'].append(copy.deepcopy(bad['metrics'][0]))
    if malform == 'trial_bool': bad['cases'][0]['trials'] = [True]
    if malform == 'bad_digest': bad['cases'][0]['input_digest'] = 'private raw text'
    if malform == 'schema_bool': bad['schema_version'] = True
    with pytest.raises(InputError):
        compare_manifests(**{side: bad, ('current' if side == 'previous' else 'previous'): manifest})


def paths(tmp_path):
    manifest, _ = setup()
    previous, current = tmp_path / 'old.json', tmp_path / 'new.json'
    previous.write_text(json.dumps(manifest))
    current.write_text(json.dumps(manifest))
    return previous, current


def test_cli_match_changed_and_existing_output_replacement(tmp_path, capsys):
    previous, current = paths(tmp_path)
    assert main(['manifest-diff', str(previous), str(current)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'MATCH'
    value = json.loads(current.read_text())
    value['cases'].pop()
    current.write_text(json.dumps(value))
    output = tmp_path / 'report.json'
    output.write_text('OLD')
    assert main(['manifest-diff', str(previous), str(current), '--output', str(output)]) == 1
    assert json.loads(output.read_text())['status'] == 'CHANGED'
    assert not list(tmp_path.glob('.evaldenom-*'))


@pytest.mark.parametrize('bad', ['{', '{"SECRET":1,"SECRET":2}', 'NaN', '[]'])
def test_cli_input_error_keeps_report_and_omits_private_payload(tmp_path, capsys, bad):
    previous, current = paths(tmp_path)
    current.write_text(bad)
    output = tmp_path / 'report.json'
    output.write_text('KEEP')
    with pytest.raises(SystemExit) as error:
        main(['manifest-diff', str(previous), str(current), '--output', str(output)])
    assert error.value.code == 2 and output.read_text() == 'KEEP'
    captured = capsys.readouterr()
    assert not captured.out and 'SECRET' not in captured.err


@pytest.mark.parametrize('alias', ['direct', 'symlink'])
def test_cli_never_replaces_either_input(tmp_path, alias):
    previous, current = paths(tmp_path)
    output = current
    if alias == 'symlink':
        output = tmp_path / 'alias.json'
        output.symlink_to(current)
    before = current.read_bytes()
    with pytest.raises(SystemExit):
        main(['manifest-diff', str(previous), str(current), '--output', str(output)])
    assert current.read_bytes() == before


def test_separately_ready_exports_do_not_approve_contract_drift():
    from evaldenom.core import audit
    previous, rows = setup()
    proposed = copy.deepcopy(previous)
    proposed['cases'].pop()  # An omitted hard case cannot be hidden by two READY labels.
    proposed_rows = [(line, row) for line, row in rows if row['id'] == 'a']
    assert audit(previous, {'a': rows, 'b': rows})['status'] == 'READY'
    assert audit(proposed, {'a': proposed_rows, 'b': proposed_rows})['status'] == 'READY'
    drift = compare_manifests(previous, proposed)
    assert drift['status'] == 'CHANGED'
    assert drift['changes'] == [{'code': 'CASE_REMOVED', 'id': 'b'}]
    assert drift['previous']['observations'] == 3 and drift['current']['observations'] == 2
    # A direct export audit under the unchanged intended plan still blocks.
    assert audit(previous, {'a': rows, 'b': proposed_rows})['status'] == 'BLOCKED'


def test_metric_order_reversal_and_no_bound_match_without_mutation():
    previous, _ = setup()
    previous['metrics'].append({'name': 'latency', 'grader': 'clock-v1', 'direction': 'lower'})
    current = copy.deepcopy(previous)
    current['metrics'].reverse()
    assert compare_manifests(previous, current)['status'] == 'MATCH'


def test_report_changes_are_deterministic_under_input_order():
    previous, _ = setup()
    current = copy.deepcopy(previous)
    for case in current['cases']:
        case['trials'] = [3, 4]
    expected = compare_manifests(previous, current)['changes']
    previous['cases'].reverse()
    current['cases'].reverse()
    assert compare_manifests(previous, current)['changes'] == expected


def test_cli_output_failure_keeps_previous_report(tmp_path, capsys, monkeypatch):
    import evaldenom.cli as cli
    previous, current = paths(tmp_path)
    output = tmp_path / 'report.json'
    output.write_text('KEEP')
    def refuse_replace(*_):
        raise OSError('SECRET filesystem details')
    monkeypatch.setattr(cli.os, 'replace', refuse_replace)
    with pytest.raises(SystemExit) as error:
        main(['manifest-diff', str(previous), str(current), '--output', str(output)])
    assert error.value.code == 2 and output.read_text() == 'KEEP'
    assert not list(tmp_path.glob('.evaldenom-*'))
    captured = capsys.readouterr()
    assert captured.out == '' and 'SECRET' not in captured.err
    assert 'no comparison verdict published' in captured.err


def test_cli_invalid_previous_keeps_report(tmp_path, capsys):
    previous, current = paths(tmp_path)
    previous.write_text('{"PRIVATE": 1, "PRIVATE": 2}')
    output = tmp_path / 'report.json'
    output.write_text('KEEP')
    with pytest.raises(SystemExit) as error:
        main(['manifest-diff', str(previous), str(current), '--output', str(output)])
    assert error.value.code == 2 and output.read_text() == 'KEEP'
    assert 'PRIVATE' not in capsys.readouterr().err


def test_cli_previous_input_alias_is_also_preserved(tmp_path):
    previous, current = paths(tmp_path)
    before = previous.read_bytes()
    with pytest.raises(SystemExit):
        main(['manifest-diff', str(previous), str(current), '--output', str(previous)])
    assert previous.read_bytes() == before
