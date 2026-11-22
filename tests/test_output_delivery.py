"""Output completion is part of the CLI verdict, not interpreter shutdown."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from evaldenom import cli as cli_module
from evaldenom.cli import main
from test_cli import files


class FailedStream(io.StringIO):
    def __init__(self, failure):
        super().__init__()
        self.failure = failure

    def write(self, text):
        if self.failure == 'write':
            raise OSError('PRIVATE-PATH')
        if self.failure == 'closed':
            raise ValueError('PRIVATE-PATH')
        if self.failure == 'short':
            return super().write(text[:-1])
        if self.failure == 'none':
            return None
        return super().write(text)

    def flush(self):
        if self.failure == 'flush':
            raise OSError('PRIVATE-PATH')


@pytest.mark.parametrize('failure', ['write', 'closed', 'short', 'none', 'flush'])
@pytest.mark.parametrize('command', ['audit', 'manifest-diff', 'help', 'subhelp', 'invalid'])
def test_embedded_main_rejects_incomplete_output(tmp_path, monkeypatch, failure, command):
    manifest, a, b = files(tmp_path)
    arguments = {
        'audit': ['audit', str(manifest), '--run', 'a='+str(a), '--run', 'b='+str(b)],
        'manifest-diff': ['manifest-diff', str(manifest), str(manifest)],
        'help': ['--help'], 'subhelp': ['audit', '--help'], 'invalid': ['INVALID'],
    }[command]
    stream, diagnostic = FailedStream(failure), io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stream)
    monkeypatch.setattr(sys, 'stderr', stream if command == 'invalid' else diagnostic)
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert not stream.closed
    assert sys.stdout is stream
    assert 'PRIVATE' not in diagnostic.getvalue()


def test_terminating_boundary_detaches_failed_flush_only(monkeypatch):
    good, bad = io.StringIO(), FailedStream('flush')
    monkeypatch.setattr(sys, 'stdout', good)
    monkeypatch.setattr(sys, 'stderr', bad)
    assert cli_module.cli(['--help']) == 2
    assert sys.stdout is good and not good.closed
    assert sys.stderr is None
    assert not bad.closed


def test_failed_diagnostic_does_not_replace_valid_atomic_file(tmp_path, monkeypatch):
    manifest, a, b = files(tmp_path)
    target = tmp_path/'output.json'
    target.write_text('OLD', encoding='utf-8')
    monkeypatch.setattr(sys, 'stdout', FailedStream('write'))
    assert main(['audit', str(manifest), '--run', 'a='+str(a), '--run', 'b='+str(b),
                 '--output', str(target)]) == 0
    assert json.loads(target.read_text())['status'] == 'READY'
    assert not list(tmp_path.glob('.evaldenom-*'))


@pytest.mark.skipif(not Path('/dev/full').exists(), reason='requires Linux /dev/full')
@pytest.mark.parametrize('unbuffered', [False, True])
@pytest.mark.parametrize('command', ['help', 'subhelp', 'invalid', 'ready', 'blocked', 'match', 'changed'])
def test_real_process_output_failure_exit2(tmp_path, unbuffered, command):
    manifest, a, b = files(tmp_path)
    changed = tmp_path/'changed.json'
    value = json.loads(manifest.read_text())
    value['cases'][0]['trials'].append(99)
    changed.write_text(json.dumps(value), encoding='utf-8')
    if command == 'blocked':
        b.write_text('', encoding='utf-8')
    args = {
        'help': ['--help'], 'subhelp': ['audit', '--help'], 'invalid': ['INVALID'],
        'ready': ['audit', str(manifest), '--run', 'a='+str(a), '--run', 'b='+str(b)],
        'blocked': ['audit', str(manifest), '--run', 'a='+str(a), '--run', 'b='+str(b)],
        'match': ['manifest-diff', str(manifest), str(manifest)],
        'changed': ['manifest-diff', str(manifest), str(changed)],
    }[command]
    launchers = [[sys.executable, '-m', 'evaldenom']]
    if os.environ.get('EVALDENOM_CONSOLE'):
        launchers.append([os.environ['EVALDENOM_CONSOLE']])
    for prefix in launchers:
        env = dict(os.environ)
        if unbuffered:
            env['PYTHONUNBUFFERED'] = '1'
        else:
            env.pop('PYTHONUNBUFFERED', None)
        with open('/dev/full', 'w') as full:
            run = subprocess.run(prefix+args, cwd=tmp_path, env=env,
                                 stdout=subprocess.PIPE if command == 'invalid' else full,
                                 stderr=full if command == 'invalid' else subprocess.PIPE,
                                 text=True)
        assert run.returncode == 2, (prefix, command, run.stderr)
        if run.stderr is not None:
            assert 'Traceback' not in run.stderr and 'Exception ignored' not in run.stderr
            assert 'PRIVATE' not in run.stderr


@pytest.mark.parametrize('failure', ['write', 'closed', 'short', 'none', 'flush'])
@pytest.mark.parametrize('command', ['freeze', 'promptfoo-freeze', 'promptfoo-audit'])
def test_other_commands_check_atomic_and_stdout_delivery(tmp_path, monkeypatch, failure, command):
    from test_promptfoo_cli import setup_files, audit_args
    paths = setup_files(tmp_path)
    target = tmp_path/'kept.json'
    target.write_text('KEEP', encoding='utf-8')
    failed = FailedStream(failure)
    if command == 'promptfoo-audit':
        args = audit_args(paths)
        monkeypatch.setattr(sys, 'stdout', failed)
    else:
        if command == 'freeze':
            cases = tmp_path/'cases.jsonl'
            cases.write_text(json.dumps({'id':'a', 'input':{}, 'trials':[1]}), encoding='utf-8')
            metrics = tmp_path/'metrics.json'
            metrics.write_text('[{"name":"m","grader":"g","direction":"higher"}]', encoding='utf-8')
            args = ['freeze', str(cases), '--metrics', str(metrics), '--output', str(target)]
        else:
            args = ['promptfoo-freeze', str(paths[0]), '--grader', 'g', '--output', str(target)]
        real_factory = cli_module.tempfile.NamedTemporaryFile
        class Proxy:
            def __enter__(self):
                self.stream = real_factory(mode='w', encoding='utf-8', dir=tmp_path,
                                           prefix='.evaldenom-', delete=False)
                self.name = self.stream.name
                return self
            def __exit__(self, *unused):
                self.stream.close()
            def write(self, text):
                return failed.write(text)
            def flush(self):
                return failed.flush()
        monkeypatch.setattr(cli_module.tempfile, 'NamedTemporaryFile', lambda **kwargs: Proxy())
    diagnostic = io.StringIO()
    monkeypatch.setattr(sys, 'stderr', diagnostic)
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert target.read_text(encoding='utf-8') == 'KEEP'
    assert not list(tmp_path.glob('.evaldenom-*'))
    assert 'PRIVATE' not in diagnostic.getvalue()
