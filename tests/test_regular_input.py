"""Regular file admission happens before either JSON reader consumes text."""
import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from evaldenom.core import InputError, read_json, read_jsonl


@pytest.mark.skipif(not hasattr(os, 'mkfifo') or not hasattr(os, 'O_NONBLOCK'), reason='POSIX FIFO')
@pytest.mark.parametrize('reader', ['read_json', 'read_jsonl'])
def test_writerless_fifo_and_alias_deadline(tmp_path, reader):
    fifo = tmp_path / 'private-case-id.fifo'
    os.mkfifo(fifo)
    alias = tmp_path / 'alias'
    alias.symlink_to(fifo)
    for path in (fifo, alias):
        script = ('import sys;from evaldenom.core import ' + reader + ',InputError\n'
                  'try:' + reader + '(sys.argv[1])\n'
                  'except InputError as e:print(e);sys.exit(2)')
        result = subprocess.run([sys.executable, '-c', script, str(path)],
                                capture_output=True, text=True, timeout=3)
        assert result.returncode == 2
        assert result.stdout == 'input must be a regular file\n'
        assert result.stderr == ''


@pytest.mark.skipif(not hasattr(os, 'mkfifo') or not hasattr(os, 'O_NONBLOCK'), reason='POSIX FIFO')
@pytest.mark.parametrize('role', ['cases', 'metrics', 'previous', 'current'])
def test_cli_special_input_preserves_output(tmp_path, role):
    fifo = tmp_path / 'private.fifo'
    os.mkfifo(fifo)
    cases = tmp_path / 'cases.jsonl'
    cases.write_text('{"id":"a","input":{},"trials":[1]}\n', encoding='utf-8')
    metrics = tmp_path / 'metrics.json'
    metrics.write_text('[{"name":"score","direction":"higher","grader":"g"}]', encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}', encoding='utf-8')
    output = tmp_path / 'output.json'
    output.write_bytes(b'KEEP')
    if role in ('cases', 'metrics'):
        args = ['freeze', str(fifo if role == 'cases' else cases), '--metrics',
                str(fifo if role == 'metrics' else metrics)]
    else:
        args = ['manifest-diff', str(fifo if role == 'previous' else manifest),
                str(fifo if role == 'current' else manifest)]
    result = subprocess.run([sys.executable, '-m', 'evaldenom', *args, '--output', str(output)],
                            capture_output=True, text=True, timeout=3)
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'regular file' in result.stderr
    assert 'private' not in result.stderr
    assert 'Traceback' not in result.stderr
    assert output.read_bytes() == b'KEEP'


@pytest.mark.parametrize('reader,raw,expected', [
    (read_json, b'{"x":1}\r\n', {'x': 1}),
    (read_jsonl, b'\r\n{"x":1}\r\n\r\n{"x":2}\r\n', [(2, {'x': 1}), (4, {'x': 2})]),
])
def test_regular_text_and_symlink_keep_physical_lines(tmp_path, reader, raw, expected):
    source = tmp_path / 'input'
    source.write_bytes(raw)
    assert reader(source) == expected
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(source)
    except OSError:
        pytest.skip('symlinks unavailable')
    assert reader(alias) == expected


@pytest.mark.parametrize('reader', [read_json, read_jsonl])
def test_descriptor_not_path_decides_and_closes(tmp_path, reader):
    source = tmp_path / 'input'
    source.write_text('{}\n', encoding='utf-8')
    original = os.fstat
    with patch('evaldenom.core.os.fstat', side_effect=lambda fd: os.stat_result((stat.S_IFIFO, *original(fd)[1:]))), pytest.raises(InputError, match='regular file'):
        reader(source)
    descriptor_dir = Path('/proc/self/fd')
    if descriptor_dir.exists():
        count = len(list(descriptor_dir.iterdir()))
        for _ in range(30):
            with patch('evaldenom.core.os.fstat', side_effect=OSError('PRIVATE')), pytest.raises(InputError, match='cannot read UTF-8'):
                reader(source)
        assert len(list(descriptor_dir.iterdir())) == count


@pytest.mark.parametrize('reader', [read_json, read_jsonl])
def test_devices_missing_and_directory_are_input_errors(tmp_path, reader):
    paths = [tmp_path, tmp_path / 'missing']
    if Path('/dev/null').exists():
        paths.append(Path('/dev/null'))
    for path in paths:
        with pytest.raises(InputError):
            reader(path)


def test_opener_retains_nonblocking_flag(tmp_path):
    path = tmp_path / 'input'
    path.write_text('{}', encoding='utf-8')
    original = os.open
    with patch('evaldenom.core.os.open', wraps=original) as opened:
        assert read_json(path) == {}
    assert opened.call_count == 1
    if hasattr(os, 'O_NONBLOCK'):
        assert opened.call_args.args[1] & os.O_NONBLOCK
