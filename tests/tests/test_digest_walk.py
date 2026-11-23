"""Digest validation visits every node without copying a container's siblings."""
import hashlib
import json
import random
import tracemalloc
from unittest.mock import patch

import pytest

from evaldenom.core import InputError, input_digest


def reference(value):
    text = json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)
    return 'pyjson-v1:' + hashlib.sha256(text.encode('ascii')).hexdigest()


def test_seeded_nested_and_wide_json_digest_parity():
    rng = random.Random(20261123)
    atoms = [None, True, False, 0, -1, 1.25, '', 'é', '\ud800', 'a\nb']

    def value(depth):
        if not depth or rng.random() < 0.5:
            return rng.choice(atoms)
        if rng.random() < 0.5:
            return [value(depth - 1) for _ in range(rng.randrange(8))]
        return {str(i): value(depth - 1) for i in range(rng.randrange(8))}

    for _ in range(1000):
        item = value(5)
        assert input_digest(item) == reference(item)
    wide = [None] * 100000
    assert input_digest(wide) == reference(wide)


@pytest.mark.parametrize('bad', [(1, 2), {1: 'value'}, float('nan'), float('inf'), object()])
def test_invalid_child_at_either_edge_or_in_nested_siblings(bad):
    for wrapped in ([bad, None], [None, bad], {'a': None, 'b': [None, bad]},
                    [None, {'tail': [bad]}]):
        with pytest.raises(InputError):
            input_digest(wrapped)


def test_shared_child_revisited_without_changing_digest():
    shared = {'x': [None, 'text', 1]}
    value = [shared, shared, {'again': shared}]
    assert input_digest(value) == reference(value)
    assert value[0] is shared and value[1] is shared


@pytest.mark.parametrize('dictionary', [False, True])
def test_cycles_still_rejected_before_walk(dictionary):
    value = {} if dictionary else []
    if dictionary:
        value['self'] = value
    else:
        value.append(value)
    with pytest.raises(InputError, match='serialization'):
        input_digest(value)


def test_validation_walk_peak_does_not_scale_with_list_width():
    # Isolate validation allocations, not JSON serialization or caller storage.
    # The mocked serializer is not used in any digest/parity correctness test.
    peaks = []
    for width in (1000, 100000):
        value = [None] * width
        with patch('evaldenom.core.json.dumps', return_value='null'):
            tracemalloc.start()
            try:
                assert input_digest(value) == reference(None)
                peaks.append(tracemalloc.get_traced_memory()[1])
            finally:
                tracemalloc.stop()
    assert peaks[1] < peaks[0] + 32768, peaks


def test_late_invalid_child_not_skipped_by_walk():
    # json.dumps accepts tuples; the strict API must still reject them even
    # after visiting a large valid prefix or a deeply nested dictionary child.
    for value in ([None] * 10000 + [(1,)], {'x': [None] * 10000 + [(1,)]}):
        with pytest.raises(InputError, match='JSON values only'):
            input_digest(value)


def test_multiple_invalid_nodes_keep_legacy_reverse_visit_diagnostic():
    for value, message in [
        ([(1,), {1: 'bad key'}], 'object keys'),
        ([{1: 'bad key'}, (1,)], 'JSON values only'),
        ({'first': (1,), 'last': {1: 'bad key'}}, 'object keys'),
        ({'first': {1: 'bad key'}, 'last': (1,)}, 'JSON values only'),
    ]:
        with pytest.raises(InputError, match=message):
            input_digest(value)


@pytest.mark.parametrize('override', ['iter', 'reversed'])
def test_list_subclass_cannot_hide_invalid_child(override):
    class HiddenIteration(list):
        def __iter__(self):
            return iter(())

    class HiddenReverse(list):
        def __reversed__(self):
            return iter(())

    cls = HiddenIteration if override == 'iter' else HiddenReverse
    with pytest.raises(InputError, match='JSON values only'):
        input_digest(cls([(1,)]))


def test_dict_subclass_cannot_hide_invalid_keys_or_values():
    class HiddenDict(dict):
        def __iter__(self):
            return iter(())

        def values(self):
            return iter(())

    for value in (HiddenDict({1: 'value'}), HiddenDict({'key': (1,)})):
        with pytest.raises(InputError):
            input_digest(value)
