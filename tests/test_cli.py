import json
import pytest
from evaldenom.cli import main
from evaldenom.core import InputError, input_digest, read_jsonl
from test_contract import setup


def files(tmp_path):
    m, rows = setup()
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(m))
    a, b = tmp_path / 'a.jsonl', tmp_path / 'b.jsonl'
    for path in (a, b):
        path.write_text('\n'.join(json.dumps(row) for _, row in rows))
    return manifest, a, b


def test_cli_ready_and_blocked_have_distinct_status(tmp_path, capsys):
    m, a, b = files(tmp_path)
    assert main(['audit', str(m), '--run', 'a=' + str(a), '--run', 'b=' + str(b)]) == 0
    ready = json.loads(capsys.readouterr().out)
    assert ready['status'] == 'READY'
    b.write_text('')
    assert main(['audit', str(m), '--run', 'a=' + str(a), '--run', 'b=' + str(b)]) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'BLOCKED'


@pytest.mark.parametrize('bad', ['{"SECRET":1,"SECRET":2}', '{', '[]', 'NaN'])
def test_bad_input_never_overwrites_output_or_echoes_content(tmp_path, capsys, bad):
    m, a, b = files(tmp_path)
    b.write_text(bad)
    output = tmp_path / 'result.json'
    output.write_text('KEEP')
    with pytest.raises(SystemExit) as error:
        main(['audit', str(m), '--run', 'a=' + str(a), '--run', 'b=' + str(b), '--output', str(output)])
    assert error.value.code == 2
    assert output.read_text() == 'KEEP'
    out = capsys.readouterr()
    assert not out.out and 'SECRET' not in out.err


def test_existing_output_replaced_only_after_complete_audit(tmp_path):
    m, a, b = files(tmp_path)
    output = tmp_path / 'result.json'
    output.write_text('OLD')
    assert main(['audit', str(m), '--run', 'a=' + str(a), '--run', 'b=' + str(b), '--output', str(output)]) == 0
    assert json.loads(output.read_text())['status'] == 'READY'
    assert not list(tmp_path.glob('.evaldenom-*'))


def test_input_path_cannot_be_replaced_by_report(tmp_path):
    m, a, b = files(tmp_path)
    before = a.read_bytes()
    with pytest.raises(SystemExit):
        main(['audit', str(m), '--run', 'a=' + str(a), '--run', 'b=' + str(b), '--output', str(a)])
    assert a.read_bytes() == before


@pytest.mark.parametrize('entry', ['same=', '=path', 'path', 'same=other'])
def test_duplicate_or_malformed_run_routes_error(tmp_path, entry):
    m, a, b = files(tmp_path)
    with pytest.raises(SystemExit) as error:
        main(['audit', str(m), '--run', 'same=' + str(a), '--run', entry])
    assert error.value.code == 2


def test_freeze_does_not_write_prompt_text(tmp_path):
    cases = tmp_path / 'cases.jsonl'
    cases.write_text(json.dumps({'id': 'a', 'input': {'prompt': 'PRIVATE-CONTENT'}, 'trials': [2, 1]}))
    metrics = tmp_path / 'metrics.json'
    metrics.write_text(json.dumps([{'name': 'm', 'grader': 'g', 'direction': 'lower'}]))
    out = tmp_path / 'manifest.json'
    assert main(['freeze', str(cases), '--metrics', str(metrics), '--output', str(out)]) == 0
    assert 'PRIVATE-CONTENT' not in out.read_text()
    assert json.loads(out.read_text())['cases'][0]['trials'] == [1, 2]


def test_blank_lines_preserve_physical_line(tmp_path):
    path = tmp_path / 'cases.jsonl'
    path.write_text('\n{"a":1}\n\n{"b":2}')
    assert [line for line, _ in read_jsonl(path)] == [2, 4]


def test_cycles_and_nonjson_python_values_fail_closed():
    cycle = []
    cycle.append(cycle)
    for value in [cycle, (1, 2), {1: 'value'}, float('inf')]:
        with pytest.raises(InputError):
            input_digest(value)
