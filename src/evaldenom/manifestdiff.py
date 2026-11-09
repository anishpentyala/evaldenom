"""Compare prospective evaluation contracts without looking at run scores.

MATCH means the declared cases, trials, input digests, clusters and metric
contracts agree. It is not an audit of exports or approval of a changed plan.
"""
from .core import input_digest, validate_manifest


def compare_manifests(previous, current):
    """Return deterministic contract drift, without modifying either manifest.

    Manifest list order and trial order do not change the declared contract.
    A missing bound differs from an explicit bound, including zero. Numeric
    bound spellings such as 0 and 0.0 keep ordinary numeric equality, consistent
    with the core audit's score checks. No cases are aligned by position.
    """
    old_cases, old_metrics = validate_manifest(previous)
    new_cases, new_metrics = validate_manifest(current)
    changes = []

    def change(code, **identity):
        changes.append({'code': code, **identity})

    for ident in sorted(old_cases.keys() | new_cases.keys()):
        if ident not in old_cases:
            change('CASE_ADDED', id=ident)
        elif ident not in new_cases:
            change('CASE_REMOVED', id=ident)
        else:
            old, new = old_cases[ident], new_cases[ident]
            if old['input_digest'] != new['input_digest']:
                change('INPUT_IDENTITY_CHANGED', id=ident)
            if ('cluster' in old) != ('cluster' in new) or old.get('cluster') != new.get('cluster'):
                change('CLUSTER_CHANGED', id=ident)
            for trial in sorted(set(old['trials']) - set(new['trials'])):
                change('TRIAL_REMOVED', id=ident, trial=trial)
            for trial in sorted(set(new['trials']) - set(old['trials'])):
                change('TRIAL_ADDED', id=ident, trial=trial)

    for name in sorted(old_metrics.keys() | new_metrics.keys()):
        if name not in old_metrics:
            change('METRIC_ADDED', metric=name)
        elif name not in new_metrics:
            change('METRIC_REMOVED', metric=name)
        else:
            old, new = old_metrics[name], new_metrics[name]
            for field, code in [('grader', 'GRADER_CHANGED'), ('direction', 'DIRECTION_CHANGED'),
                                ('min', 'MINIMUM_CHANGED'), ('max', 'MAXIMUM_CHANGED')]:
                if (field in old) != (field in new) or old.get(field) != new.get(field):
                    change(code, metric=name)

    def counts(cases, metrics):
        return {'cases': len(cases), 'observations': sum(len(c['trials']) for c in cases.values()),
                'metrics': len(metrics)}

    return {
        'schema_version': 1,
        'kind': 'evaldenom.manifest-comparison',
        'status': 'CHANGED' if changes else 'MATCH',
        'previous': counts(old_cases, old_metrics),
        'current': counts(new_cases, new_metrics),
        'source_manifest_digests': {'previous': input_digest(previous), 'current': input_digest(current)},
        'changes': changes,
        'limitations': [
            'MATCH compares supplied prospective contracts, not export coverage, actual model inputs or result quality.',
            'CHANGED describes drift; it does not approve a new denominator, rubric or experiment plan.',
            'Case, metric and cluster labels and input digests are caller claims, not provenance attestation.',
            'Source digests identify supplied manifests, including list order; they can differ when contracts MATCH.',
            'Reports include case and metric identifiers; review them before sharing. Raw inputs, digest values per case and scores are not included.',
        ],
    }
