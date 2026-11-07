import copy
import json
import pytest
from evaldenom.core import InputError, audit, freeze, input_digest, loads


def setup():
    metrics = [{'name': 'quality', 'direction': 'higher', 'grader': 'rubric-v1', 'min': 0, 'max': 1}]
    cases = [(1, {'id': 'a', 'input': {'question': 'one'}, 'trials': [1, 2], 'cluster': 'doc1'}),
             (2, {'id': 'b', 'input': {'question': 'two'}, 'trials': [1], 'cluster': 'doc2'})]
    manifest = freeze(cases, metrics)
    rows = []
    for case in manifest['cases']:
        for trial in case['trials']:
            rows.append((len(rows) + 1, {'id': case['id'], 'trial': trial,
                'input_digest': case['input_digest'], 'cluster': case['cluster'],
                'metrics': {'quality': {'status': 'ok', 'value': .5,
                                        'grader': 'rubric-v1', 'direction': 'higher'}}}))
    return manifest, rows


def codes(result):
    return {item['code'] for item in result['runs']['candidate']['findings']}


def check(change):
    m, rows = setup()
    candidate = copy.deepcopy(rows)
    change(candidate)
    return audit(m, {'baseline': rows, 'candidate': candidate})


def test_full_coverage_ready_order_independent():
    m, rows = setup()
    result = audit(m, {'baseline': rows, 'candidate': list(reversed(rows))})
    assert result['status'] == 'READY'
    assert all(r['expected_observations'] == 3 for r in result['runs'].values())
    assert 'value' not in json.dumps(result)


def test_missing_hard_case_never_disappears_into_paired_subset():
    result = check(lambda rows: rows.pop())
    assert result['status'] == 'BLOCKED'
    assert 'MISSING_OBSERVATION' in codes(result)
    assert result['runs']['candidate']['expected_observations'] == 3
    assert result['runs']['candidate']['matched_unique_identities'] == 2


@pytest.mark.parametrize('changed', [False, True])
def test_duplicate_even_identical_is_not_last_row_wins(changed):
    def change(rows):
        duplicate = copy.deepcopy(rows[0][1])
        if changed:
            duplicate['metrics']['quality']['value'] = 1
        rows.append((4, duplicate))
    assert 'DUPLICATE_OBSERVATION' in codes(check(change))


@pytest.mark.parametrize('field,value,code', [
    ('id', 'unknown', 'UNEXPECTED_OBSERVATION'), ('trial', 3, 'UNEXPECTED_OBSERVATION'),
    ('input_digest', 'pyjson-v1:' + '0' * 64, 'INPUT_IDENTITY_MISMATCH'),
    ('cluster', 'other', 'CLUSTER_MISMATCH')])
def test_identity_contract_violation(field, value, code):
    assert code in codes(check(lambda rows: rows[0][1].update({field: value})))


@pytest.mark.parametrize('field,value,code', [
    ('grader', 'rubric-v2', 'GRADER_MISMATCH'), ('direction', 'lower', 'DIRECTION_MISMATCH'),
    ('status', 'error', 'METRIC_ERROR'), ('status', 'missing', 'METRIC_MISSING'),
    ('value', True, 'INVALID_SCORE'), ('value', '0.5', 'INVALID_SCORE'),
    ('value', -1, 'SCORE_OUT_OF_BOUNDS'), ('value', 2, 'SCORE_OUT_OF_BOUNDS')])
def test_score_contract_violation(field, value, code):
    def change(rows):
        rows[0][1]['metrics']['quality'][field] = value
    assert code in codes(check(change))


def test_absent_metric_not_imputed_to_zero():
    assert 'MISSING_METRIC' in codes(check(lambda rows: rows[0][1]['metrics'].clear()))


def test_unknown_metric_is_visible():
    def change(rows):
        rows[0][1]['metrics']['SECRET-METRIC'] = {'anything': 'not consumed'}
    assert 'UNEXPECTED_METRIC' in codes(check(change))


def test_missing_cluster_not_inherited_from_other_run():
    assert 'CLUSTER_MISMATCH' in codes(check(lambda rows: rows[0][1].pop('cluster')))


def test_scores_can_change_without_identity_failure():
    def change(rows):
        rows[0][1]['metrics']['quality']['value'] = 1
    assert check(change)['status'] == 'READY'  # Not an improvement verdict.


def test_grader_contract_is_not_input_payload():
    m, rows = setup()
    before = copy.deepcopy((m, rows))
    audit(m, {'a': rows, 'b': rows})
    assert (m, rows) == before


@pytest.mark.parametrize('bad', [True, False, 0, -1, 1.5, '1', None])
def test_trials_never_coerced(bad):
    with pytest.raises(InputError):
        freeze([(1, {'id': 'a', 'input': {}, 'trials': [bad]})],
               [{'name': 'm', 'grader': 'g', 'direction': 'higher'}])


@pytest.mark.parametrize('bad', ['', 1, True, None, [], {}])
def test_case_ids_are_typed_nonempty_strings(bad):
    with pytest.raises(InputError):
        freeze([(1, {'id': bad, 'input': {}, 'trials': [1]})],
               [{'name': 'm', 'grader': 'g', 'direction': 'higher'}])


@pytest.mark.parametrize('text', ['{"x":1,"x":1}', '{"x":{"y":1,"y":2}}', '{"x":NaN}', '{"x":Infinity}'])
def test_ambiguous_or_non_json_data_rejected_without_echo(text):
    with pytest.raises(InputError) as error:
        loads(text)
    assert '"x"' not in str(error.value)


def test_input_digest_is_structured_not_stringified():
    assert input_digest({'a': 1, 'b': 2}) == input_digest({'b': 2, 'a': 1})
    assert len({input_digest(x) for x in [1, 1., True, '1', [1], {'a': 1}]}) == 6
    assert input_digest([1, 2]) != input_digest([2, 1])


def test_repetition_is_required_even_with_same_case_ids():
    result = check(lambda rows: rows.pop(1))
    assert result['runs']['candidate']['findings'] == [
        {'code': 'MISSING_OBSERVATION', 'id': 'a', 'trial': 2}]


def test_empty_run_blocked_empty_manifest_error():
    m, rows = setup()
    assert audit(m, {'a': rows, 'candidate': []})['status'] == 'BLOCKED'
    m['cases'] = []
    with pytest.raises(InputError):
        audit(m, {'a': rows, 'b': rows})


def test_manifest_duplicate_case_is_not_coverage():
    m, rows = setup()
    m['cases'].append(copy.deepcopy(m['cases'][0]))
    with pytest.raises(InputError):
        audit(m, {'a': rows, 'b': rows})


def test_single_run_cannot_certify_comparison():
    m, rows = setup()
    with pytest.raises(InputError):
        audit(m, {'a': rows})
