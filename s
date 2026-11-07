"""A small strict contract between an intended evaluation and run exports.

No model calls, result selection, imputation, retry, statistics or data editing.
Digests bind the supplied JSON values, not the actual prompts a model saw.
"""
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path


class InputError(ValueError):
    """Unusable input; diagnostics intentionally omit captured values."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError('repeated JSON object member')
        result[key] = value
    return result


def _constant(_):
    raise InputError('non-JSON numeric constant')


def loads(text):
    try:
        return json.loads(text, object_pairs_hook=_unique, parse_constant=_constant)
    except InputError:
        raise
    except (ValueError, RecursionError):
        raise InputError('JSON decoding failed or exceeded runtime limits') from None


def read_json(path):
    try:
        return loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError):
        raise InputError('cannot read UTF-8 JSON input') from None


def read_jsonl(path):
    rows = []
    try:
        with open(path, encoding='utf-8') as stream:
            for line, text in enumerate(stream, 1):
                if not text.strip():
                    continue
                try:
                    rows.append((line, loads(text)))
                except InputError as error:
                    raise InputError('JSONL line %d: %s' % (line, error)) from None
    except (OSError, UnicodeError):
        raise InputError('cannot read UTF-8 JSONL input') from None
    return rows


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or not set(required) <= set(value):
        raise InputError('object fields do not match the declared format')


def _label(value):
    if not isinstance(value, str) or not value:
        raise InputError('identifiers must be nonempty strings')
    return value


def _trials(values):
    if (not isinstance(values, list) or not values
            or any(type(v) is not int or v < 1 for v in values)
            or len(set(values)) != len(values)):
        raise InputError('trials must be a nonempty unique list of positive integers')
    return sorted(values)


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _metrics(value):
    if not isinstance(value, list) or not value:
        raise InputError('metrics must be a nonempty list')
    result = {}
    for item in value:
        _keys(item, ('name', 'direction', 'grader'), ('min', 'max'))
        name = _label(item['name'])
        _label(item['grader'])
        if item['direction'] not in ('higher', 'lower'):
            raise InputError('metric direction must be higher or lower')
        if name in result:
            raise InputError('metric names must be unique')
        if any(not _number(item[k]) for k in ('min', 'max') if k in item):
            raise InputError('metric bounds must be finite real numbers')
        if 'min' in item and 'max' in item and item['min'] > item['max']:
            raise InputError('metric minimum exceeds maximum')
        result[name] = dict(item)
    return result


def input_digest(value):
    """Versioned Python JSON canonical form; not cross-language JCS.

    JSON types and array order are kept. Object order is ignored. Numbers
    1 and 1.0 differ. Raw whitespace/escape spelling is not represented.
    """
    # Serialize first: JSON's circular-reference check prevents a cyclic
    # Python API input from making the iterative type check loop forever.
    try:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True,
                          separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise InputError('input serialization failed or exceeded runtime limits') from None
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if any(type(k) is not str for k in item):
                raise InputError('input object keys must be strings')
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif type(item) not in (type(None), bool, str, int, float):
            raise InputError('input must contain JSON values only')
        elif type(item) is float and not math.isfinite(item):
            raise InputError('input numbers must be finite')
    return 'pyjson-v1:' + hashlib.sha256(text.encode('ascii')).hexdigest()


_DIGEST = re.compile(r'pyjson-v1:[0-9a-f]{64}\Z')


def freeze(case_rows, metric_specs):
    """Freeze intended cases from [(physical_line, JSON_object),...]."""
    metrics = _metrics(metric_specs)
    cases, seen = [], set()
    for line, row in case_rows:
        _keys(row, ('id', 'input', 'trials'), ('cluster',))
        ident = _label(row['id'])
        if ident in seen:
            raise InputError('duplicate intended case identity at line %d' % line)
        seen.add(ident)
        case = {'id': ident, 'input_digest': input_digest(row['input']),
                'trials': _trials(row['trials'])}
        if 'cluster' in row:
            case['cluster'] = _label(row['cluster'])
        cases.append(case)
    if not cases:
        raise InputError('intended case manifest must be nonempty')
    return {'schema_version': 1, 'metrics': list(metrics.values()),
            'cases': sorted(cases, key=lambda c: c['id'])}


def validate_manifest(value):
    _keys(value, ('schema_version', 'metrics', 'cases'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise InputError('unsupported manifest schema version')
    metrics = _metrics(value['metrics'])
    if not isinstance(value['cases'], list) or not value['cases']:
        raise InputError('manifest cases must be nonempty')
    cases = {}
    for case in value['cases']:
        _keys(case, ('id', 'input_digest', 'trials'), ('cluster',))
        ident = _label(case['id'])
        if ident in cases:
            raise InputError('duplicate intended case identity')
        if not isinstance(case['input_digest'], str) or not _DIGEST.fullmatch(case['input_digest']):
            raise InputError('unsupported input digest')
        _trials(case['trials'])
        if 'cluster' in case:
            _label(case['cluster'])
        cases[ident] = case
    return cases, metrics


def audit(manifest, runs):
    """Audit named runs, returning coverage findings, never a partial score.

    runs maps a unique run name to [(physical_line, JSON_object),...].
    Malformed envelopes raise InputError. Valid incomplete/error evidence is
    reported as blocking, preserving other rows rather than fabricating success.
    """
    cases, metrics = validate_manifest(manifest)
    if not isinstance(runs, dict) or len(runs) < 2:
        raise InputError('supply at least two separately named runs')
    expected = {(ident, trial) for ident, case in cases.items() for trial in case['trials']}
    reports = {}
    for label, rows in runs.items():
        _label(label)
        counts, findings = Counter(), []
        for line, row in rows:
            _keys(row, ('id', 'trial', 'input_digest', 'metrics'), ('cluster',))
            ident = _label(row['id'])
            if type(row['trial']) is not int or row['trial'] < 1:
                raise InputError('run trial must be a positive integer')
            if not isinstance(row['input_digest'], str) or not _DIGEST.fullmatch(row['input_digest']):
                raise InputError('run input digest is malformed')
            if not isinstance(row['metrics'], dict):
                raise InputError('run metrics must be an object')
            key = (ident, row['trial'])
            counts[key] += 1
            def flag(code, metric=None):
                item = {'code': code, 'line': line, 'id': ident, 'trial': row['trial']}
                if metric is not None:
                    item['metric'] = metric
                findings.append(item)
            if key not in expected:
                flag('UNEXPECTED_OBSERVATION')
                continue
            case = cases[ident]
            if row['input_digest'] != case['input_digest']:
                flag('INPUT_IDENTITY_MISMATCH')
            if ('cluster' in row) != ('cluster' in case) or row.get('cluster') != case.get('cluster'):
                flag('CLUSTER_MISMATCH')
            for name in sorted(set(row['metrics']) - set(metrics)):
                flag('UNEXPECTED_METRIC', name)
            for name, spec in metrics.items():
                metric = row['metrics'].get(name)
                if metric is None:
                    flag('MISSING_METRIC', name)
                    continue
                _keys(metric, ('status', 'grader', 'direction'), ('value',))
                if metric['status'] not in ('ok', 'error', 'missing'):
                    raise InputError('metric status must be ok, error or missing')
                if metric['grader'] != spec['grader']:
                    flag('GRADER_MISMATCH', name)
                if metric['direction'] != spec['direction']:
                    flag('DIRECTION_MISMATCH', name)
                if metric['status'] != 'ok':
                    flag('METRIC_' + metric['status'].upper(), name)
                elif not _number(metric.get('value')):
                    flag('INVALID_SCORE', name)
                elif (('min' in spec and metric['value'] < spec['min'])
                      or ('max' in spec and metric['value'] > spec['max'])):
                    flag('SCORE_OUT_OF_BOUNDS', name)
        for ident, trial in sorted(expected - counts.keys()):
            findings.append({'code': 'MISSING_OBSERVATION', 'id': ident, 'trial': trial})
        for (ident, trial), count in sorted(counts.items()):
            if count > 1:
                findings.append({'code': 'DUPLICATE_OBSERVATION', 'id': ident,
                                 'trial': trial, 'count': count})
        reports[label] = {'expected_observations': len(expected),
                          'supplied_records': sum(counts.values()),
                          'matched_unique_identities': len(expected & counts.keys()),
                          'status': 'BLOCKED' if findings else 'READY', 'findings': findings}
    return {'schema_version': 1, 'manifest_digest': input_digest(manifest),
            'status': 'BLOCKED' if any(r['findings'] for r in reports.values()) else 'READY',
            'runs': reports,
            'limitations': [
                'READY means supplied exports match the declared contract, not that results are true or statistically comparable.',
                'Digests and grader labels are caller-supplied claims, not proof of model inputs, execution or evaluator implementation.',
                'No rows are selected, averaged, dropped, retried or rewritten. No statistical test is run.',
                'Manifest coverage is only as complete as the supplied intended cases and trials; clusters are labels, not an independence test.',
                'Reports contain case, cluster and metric identifiers; review them before sharing. Raw inputs and scores are not included.'
            ]}
