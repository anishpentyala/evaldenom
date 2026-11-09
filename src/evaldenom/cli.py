"""Offline CLI. Input errors do not replace an existing output."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from .core import InputError, audit, freeze, read_json, read_jsonl


def _write(path, text):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.evaldenom-', delete=False) as out:
            temporary = out.name
            out.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit intended evaluation coverage and identity, offline.')
    sub = parser.add_subparsers(dest='command', required=True)
    f = sub.add_parser('freeze')
    f.add_argument('cases')
    f.add_argument('--metrics', required=True)
    f.add_argument('--output', required=True)
    a = sub.add_parser('audit')
    a.add_argument('manifest')
    a.add_argument('--run', action='append', required=True, metavar='NAME=FILE')
    a.add_argument('--output')
    pf = sub.add_parser('promptfoo-freeze', help='Freeze narrow prospective inline Promptfoo tests.')
    pf.add_argument('tests')
    pf.add_argument('--grader', required=True)
    pf.add_argument('--output', required=True)
    pa = sub.add_parser('promptfoo-audit', help='Audit explicitly selected Promptfoo JSON export slices.')
    pa.add_argument('manifest')
    pa.add_argument('--run', action='append', required=True, metavar='NAME=FILE')
    pa.add_argument('--selections', required=True, help='Strict JSON run-label to provider/prompt/grader map.')
    pa.add_argument('--output')
    d = sub.add_parser('manifest-diff', help='Compare two prospective contracts, not run scores.')
    d.add_argument('previous')
    d.add_argument('current')
    d.add_argument('--output')
    args = parser.parse_args(argv)
    try:
        if args.command == 'manifest-diff':
            from .manifestdiff import compare_manifests
            if args.output and Path(args.output).resolve() in {Path(args.previous).resolve(), Path(args.current).resolve()}:
                raise InputError('output must not replace an input')
            result = compare_manifests(read_json(args.previous), read_json(args.current))
        elif args.command == 'freeze':
            if Path(args.output).resolve() in {Path(args.cases).resolve(), Path(args.metrics).resolve()}:
                raise InputError('output must not replace an input')
            result = freeze(read_jsonl(args.cases), read_json(args.metrics))
        elif args.command == 'promptfoo-freeze':
            from .promptfoo import manifest_from_inline_tests
            if Path(args.output).resolve() == Path(args.tests).resolve():
                raise InputError('output must not replace an input')
            result = manifest_from_inline_tests(read_json(args.tests), grader=args.grader)
        else:
            runs = {}
            for item in args.run:
                name, sep, path = item.partition('=')
                if not sep or not name or not path or name in runs:
                    raise InputError('run labels must be unique NAME=FILE entries')
                runs[name] = read_json(path) if args.command == 'promptfoo-audit' else read_jsonl(path)
            inputs = ({Path(args.manifest).resolve()}
                      | {Path(item.partition('=')[2]).resolve() for item in args.run})
            if args.command == 'promptfoo-audit':
                inputs.add(Path(args.selections).resolve())
            if args.output and Path(args.output).resolve() in inputs:
                raise InputError('output must not replace an input')
            if args.command == 'promptfoo-audit':
                from .promptfoo import audit_promptfoo_exports
                result = audit_promptfoo_exports(read_json(args.manifest), runs, read_json(args.selections))
            else:
                result = audit(read_json(args.manifest), runs)
        text = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
        if args.output:
            _write(args.output, text)
        else:
            print(text, end='')
        return 1 if result.get('status') in ('BLOCKED', 'CHANGED') else 0
    except InputError as error:
        # InputError messages are controlled diagnostics, never raw values.
        parser.exit(2, 'evaldenom: %s; no %s verdict published\n' % (error, 'comparison' if args.command == 'manifest-diff' else 'audit'))
    except (OSError, UnicodeError):
        parser.exit(2, 'evaldenom: input or output I/O error; no %s verdict published\n' % ('comparison' if args.command == 'manifest-diff' else 'audit'))


if __name__ == '__main__':
    raise SystemExit(main())
