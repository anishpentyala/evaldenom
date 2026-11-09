"""Same script runs against source or an installed wheel from outside the tree."""
import json
import subprocess
import sys


def test_cli_separate_plan_drift_has_its_own_exit_contract(tmp_path):
    from evaldenom.core import freeze
    previous = freeze([(1, {'id': 'easy', 'input': {'q': 'synthetic'}, 'trials': [1]}),
                       (2, {'id': 'hard', 'input': {'q': 'hard synthetic'}, 'trials': [1, 2]})],
                      [{'name': 'quality', 'grader': 'rubric-v1', 'direction': 'higher'}])
    old, new = tmp_path / 'old.json', tmp_path / 'new.json'
    old.write_text(json.dumps(previous), encoding='utf-8')
    new.write_text(json.dumps(previous), encoding='utf-8')
    def run(*args):
        return subprocess.run([sys.executable, '-m', 'evaldenom.cli', 'manifest-diff',
                               str(old), str(new), *map(str, args)],
                              capture_output=True, text=True)
    same = run()
    assert same.returncode == 0, same.stderr
    assert json.loads(same.stdout)['status'] == 'MATCH'
    previous['cases'].pop()
    new.write_text(json.dumps(previous), encoding='utf-8')
    changed = run()
    assert changed.returncode == 1, changed.stderr
    assert json.loads(changed.stdout)['changes'] == [{'code': 'CASE_REMOVED', 'id': 'hard'}]
    output = tmp_path / 'report.json'
    output.write_text('KEEP', encoding='utf-8')
    new.write_text('{"PRIVATE":1,"PRIVATE":2}', encoding='utf-8')
    invalid = run('--output', output)
    assert invalid.returncode == 2 and invalid.stdout == ''
    assert 'PRIVATE' not in invalid.stderr and output.read_text(encoding='utf-8') == 'KEEP'
