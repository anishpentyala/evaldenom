"""Coverage-index behavior for sparse, repeated and unexpected identities."""
import copy

from evaldenom import audit, freeze


def test_sparse_multi_case_trial_identity_counts_and_order():
    manifest = freeze([
        (1, {'id': 'z', 'input': {}, 'trials': [9, 2, 5]}),
        (2, {'id': 'a', 'input': {}, 'trials': [4, 1]}),
    ], [{'name': 'm', 'grader': 'v1', 'direction': 'higher'}])
    digest = manifest['cases'][0]['input_digest']
    def row(ident, trial):
        return {'id': ident, 'trial': trial, 'input_digest': digest,
                'metrics': {'m': {'status': 'ok', 'grader': 'v1',
                                  'direction': 'higher', 'value': 1}}}
    rows = [(1, row('a', 4)), (2, row('z', 2)), (3, row('z', 2)),
            (4, row('z', 7)), (5, row('unknown', 1))]
    before = copy.deepcopy((manifest, rows))
    report = audit(manifest, {'first': rows, 'second': []})
    first = report['runs']['first']
    assert first['expected_observations'] == 5
    assert first['supplied_records'] == 5
    assert first['matched_unique_identities'] == 2
    assert first['findings'] == [
        {'code': 'UNEXPECTED_OBSERVATION', 'line': 4, 'id': 'z', 'trial': 7},
        {'code': 'UNEXPECTED_OBSERVATION', 'line': 5, 'id': 'unknown', 'trial': 1},
        {'code': 'MISSING_OBSERVATION', 'id': 'a', 'trial': 1},
        {'code': 'MISSING_OBSERVATION', 'id': 'z', 'trial': 5},
        {'code': 'MISSING_OBSERVATION', 'id': 'z', 'trial': 9},
        {'code': 'DUPLICATE_OBSERVATION', 'id': 'z', 'trial': 2, 'count': 2},
    ]
    assert report['runs']['second']['matched_unique_identities'] == 0
    assert len(report['runs']['second']['findings']) == 5
    assert report['status'] == 'BLOCKED'
    assert (manifest, rows) == before


def test_short_and_long_trial_indexes_have_identical_contracts():
    for count in (1, 8, 9, 20):
        manifest = freeze([(1, {'id': 'c', 'input': {}, 'trials': list(range(count, 0, -1))})],
                          [{'name': 'm', 'grader': 'v1', 'direction': 'higher'}])
        rows = [(1, {'id': 'c', 'trial': count,
                     'input_digest': manifest['cases'][0]['input_digest'],
                     'metrics': {'m': {'status': 'ok', 'grader': 'v1',
                                       'direction': 'higher', 'value': 1}}})]
        before = copy.deepcopy(manifest)
        report = audit(manifest, {'a': rows, 'b': []})
        assert report['runs']['a']['matched_unique_identities'] == 1
        assert report['runs']['a']['expected_observations'] == count
        assert report['runs']['a']['findings'] == [
            {'code': 'MISSING_OBSERVATION', 'id': 'c', 'trial': t}
            for t in range(1, count)]
        assert manifest == before


def test_handwritten_unsorted_manifest_has_sorted_missing_findings():
    manifest = {
        'schema_version': 1,
        'cases': [
            {'id': 'z', 'input_digest': 'pyjson-v1:' + '0' * 64,
             'trials': [9, 1, 5]},
            {'id': 'a', 'input_digest': 'pyjson-v1:' + '1' * 64,
             'trials': [7, 2]},
        ],
        'metrics': [{'name': 'm', 'grader': 'v1', 'direction': 'higher'}],
    }
    before = copy.deepcopy(manifest)
    report = audit(manifest, {'a': [], 'b': []})
    expected = [
        {'code': 'MISSING_OBSERVATION', 'id': ident, 'trial': trial}
        for ident, trial in [('a', 2), ('a', 7), ('z', 1), ('z', 5), ('z', 9)]
    ]
    assert report['runs']['a']['findings'] == expected
    assert report['runs']['b']['findings'] == expected
    assert manifest == before
