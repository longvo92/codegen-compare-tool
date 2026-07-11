"""CLI entry point.

Usage:
    python -m compare_tool <old_dir> <new_dir> [--report out.html]
                           [--port 8765] [--no-browser] [--no-server]
"""

import argparse
import sys
import webbrowser
from pathlib import Path

from .report import build_report
from .scanner import scan, summarize
from .server import serve


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='compare_tool',
        description='Compare two AUTOSAR codegen folders, filtering MATLAB noise '
                    '(comments, 1-1 renames, UUIDs, timestamps, whitespace).')
    ap.add_argument('old_dir', help='previous codegen output folder')
    ap.add_argument('new_dir', help='new codegen output folder')
    ap.add_argument('--report', metavar='OUT.html', help='write HTML report of real changes')
    ap.add_argument('--port', type=int, default=8765, help='UI server port (default 8765)')
    ap.add_argument('--no-browser', action='store_true', help='do not open browser')
    ap.add_argument('--no-server', action='store_true', help='exit after scan/report (headless)')
    args = ap.parse_args(argv)

    old_root = Path(args.old_dir)
    new_root = Path(args.new_dir)
    for p, name in ((old_root, 'old_dir'), (new_root, 'new_dir')):
        if not p.is_dir():
            ap.error('{} is not a directory: {}'.format(name, p))

    print('Scanning...')

    def progress(done, total, rel):
        if done % 50 == 0 or done == total:
            print('  {}/{} {}'.format(done, total, rel))

    results = scan(old_root, new_root, progress=progress)
    counts = summarize(results)
    print('Summary: {real-change} real change, {ignorable-only} ignorable-only, '
          '{added} added, {deleted} deleted, {identical} identical'.format(**counts))
    for rel, r in sorted(results.items()):
        if r['status'] == 'real-change':
            n_real = sum(1 for h in r['hunks'] if h['kind'] == 'real') or ('binary' in r['notes'] and 1)
            print('  REAL  {} ({} hunk(s))'.format(rel, n_real))

    if args.report:
        out = Path(args.report)
        out.write_text(build_report(results, old_root, new_root), encoding='utf-8')
        print('Report written: {}'.format(out.resolve()))

    if args.no_server:
        return 1 if counts['real-change'] or counts['added'] or counts['deleted'] else 0

    httpd = serve(results, old_root, new_root, args.port)
    url = 'http://127.0.0.1:{}/'.format(args.port)
    print('UI: {} (Ctrl+C to stop)'.format(url))
    if not args.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
