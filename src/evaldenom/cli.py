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
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze':
            if Path(args.output).resolve() in {Path(args.cases).resolve(), Path(args.metrics).resolve()}:
                raise InputError('output must not replace an input')
            result = freeze(read_jsonl(args.cases), read_json(args.metrics))
        else:
            runs = {}
            for item in args.run:
                name, sep, path = item.partition('=')
                if not sep or not name or not path or name in runs:
                    raise InputError('run labels must be unique NAME=FILE entries')
                runs[name] = read_jsonl(path)
            if args.output and Path(args.output).resolve() in ({Path(args.manifest).resolve()}
                    | {Path(item.partition('=')[2]).resolve() for item in args.run}):
                raise InputError('output must not replace an input')
            result = audit(read_json(args.manifest), runs)
        text = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
        if args.output:
            _write(args.output, text)
        else:
            print(text, end='')
        return 1 if result.get('status') == 'BLOCKED' else 0
    except InputError as error:
        # InputError messages are controlled diagnostics, never raw values.
        parser.exit(2, 'evaldenom: %s; no audit verdict published\n' % error)
    except (OSError, UnicodeError):
        parser.exit(2, 'evaldenom: input or output I/O error; no audit verdict published\n')


if __name__ == '__main__':
    raise SystemExit(main())
