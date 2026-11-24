"""Native CLI streaming retains reports without retaining raw run exports."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from evaldenom import cli, core
from test_cli import files


def test_public_reader_still_returns_list(tmp_path):
    path = tmp_path / 'run'
    path.write_text('\n{}\r\n\n{}\n', encoding='utf-8')
    assert core.read_jsonl(path) == [(2, {}), (4, {})]


def test_native_audit_passes_lazy_rows_and_closes_every_iterator(tmp_path, capsys):
    manifest, a, b = files(tmp_path)
    opened, closed = [], []
    original = core._iter_jsonl

    def tracked(path):
        try:
            opened.append(path)
            yield from original(path)
        finally:
            closed.append(path)

    def checking(manifest, runs):
        assert opened == []
        assert all(not isinstance(rows, list) for rows in runs.values())
        return core.audit(manifest, runs)

    with patch.object(cli, '_iter_jsonl', tracked), patch.object(cli, 'audit', checking):
        assert cli.main(['audit', str(manifest), '--run', 'a=' + str(a),
                         '--run', 'b=' + str(b)]) == 0
    assert opened == closed == [str(a), str(b)]
    assert json.loads(capsys.readouterr().out)['status'] == 'READY'


@pytest.mark.parametrize('failure', ['envelope', 'decode', 'missing', 'manifest'])
def test_failure_preserves_output_and_closes_active_file(tmp_path, capsys, failure):
    manifest, a, b = files(tmp_path)
    if failure == 'envelope':
        a.write_text('{}\n', encoding='utf-8')
    elif failure == 'decode':
        with a.open('a', encoding='utf-8') as stream:
            stream.write('\nPRIVATE')
    elif failure == 'missing':
        b.unlink()
    else:
        manifest.write_text('{}', encoding='utf-8')
    output = tmp_path / 'output'
    output.write_bytes(b'KEEP')
    descriptor_dir = Path('/proc/self/fd')
    before = len(list(descriptor_dir.iterdir())) if descriptor_dir.exists() else None
    for _ in range(30):
        with pytest.raises(SystemExit) as error:
            cli.main(['audit', str(manifest), '--run', 'a=' + str(a),
                      '--run', 'b=' + str(b), '--output', str(output)])
        assert error.value.code == 2
    if before is not None:
        assert len(list(descriptor_dir.iterdir())) == before
    assert output.read_bytes() == b'KEEP'
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'PRIVATE' not in captured.err
    assert 'Traceback' not in captured.err


def test_lazy_decode_keeps_physical_line_and_cleanup(tmp_path):
    path = tmp_path / 'run'
    path.write_text('\n{}\n\nPRIVATE', encoding='utf-8')
    rows = core._iter_jsonl(path)
    assert next(rows) == (2, {})
    with pytest.raises(core.InputError, match='JSONL line 4: JSON decoding failed'):
        next(rows)
    assert rows.gi_frame is None


def test_freeze_still_uses_materialized_reader(tmp_path):
    cases = tmp_path / 'cases'
    cases.write_text('{"id":"a","input":{},"trials":[1]}', encoding='utf-8')
    metrics = tmp_path / 'metrics'
    metrics.write_text('[{"name":"m","grader":"g","direction":"higher"}]', encoding='utf-8')
    with patch.object(cli, '_iter_jsonl', side_effect=AssertionError('native audit only')):
        assert cli.main(['freeze', str(cases), '--metrics', str(metrics),
                         '--output', str(tmp_path / 'manifest')]) == 0


def test_core_failure_closes_all_registered_readers_without_gc(tmp_path):
    manifest, a, b = files(tmp_path)
    created = []

    class Rows:
        def __init__(self, path):
            self.closed = False
            created.append(self)
        def __iter__(self):
            return iter([(1, {})])
        def close(self):
            self.closed = True

    with patch.object(cli, '_iter_jsonl', Rows), pytest.raises(SystemExit):
        cli.main(['audit', str(manifest), '--run', 'a=' + str(a), '--run', 'b=' + str(b)])
    assert len(created) == 2
    assert all(item.closed for item in created)


@pytest.mark.skipif(not hasattr(__import__('os'), 'mkfifo') or not hasattr(__import__('os'), 'O_NONBLOCK'), reason='POSIX FIFO')
def test_native_audit_fifo_deadline_preserves_output(tmp_path):
    import os
    import subprocess
    import sys
    manifest, a, _ = files(tmp_path)
    fifo = tmp_path / 'private.fifo'
    os.mkfifo(fifo)
    output = tmp_path / 'output'
    output.write_bytes(b'KEEP')
    result = subprocess.run([sys.executable, '-m', 'evaldenom', 'audit', str(manifest),
                             '--run', 'a=' + str(a), '--run', 'b=' + str(fifo),
                             '--output', str(output)], capture_output=True, text=True, timeout=3)
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'regular file' in result.stderr
    assert 'private' not in result.stderr
    assert output.read_bytes() == b'KEEP'


def test_invalid_earlier_envelope_precedes_later_bad_json(tmp_path, capsys):
    manifest, a, b = files(tmp_path)
    a.write_text('{}\nPRIVATE', encoding='utf-8')
    b.write_text('ALSO_PRIVATE', encoding='utf-8')
    with pytest.raises(SystemExit):
        cli.main(['audit', str(manifest), '--run', 'a=' + str(a), '--run', 'b=' + str(b)])
    captured = capsys.readouterr()
    assert 'object fields do not match' in captured.err
    assert 'PRIVATE' not in captured.err
