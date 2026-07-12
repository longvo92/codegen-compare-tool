"""CLI entry point.

Usage:
    python -m compare_tool <old_dir> <new_dir> [--report out.html]
"""

import argparse
import sys
from pathlib import Path

from .report import build_report
from .scanner import scan, summarize


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='compare_tool',
        description='Compare two AUTOSAR codegen folders, filtering MATLAB noise '
                    '(comments, 1-1 renames, UUIDs, timestamps, whitespace). '
                    'Writes a self-contained HTML report.')
    ap.add_argument('old_dir', help='previous codegen output folder')
    ap.add_argument('new_dir', help='new codegen output folder')
    ap.add_argument('--report', metavar='OUT.html', default='compare_report.html',
                    help='HTML report output path (default: compare_report.html)')
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
    print('Summary: {real-change} modified, {ignorable-only} unimportant, '
          '{added} added, {deleted} deleted, {identical} identical'.format(**counts))
    for rel, r in sorted(results.items()):
        if r['status'] == 'real-change':
            n_real = sum(1 for h in r['hunks'] if h['kind'] == 'real') or ('binary' in r['notes'] and 1)
            print('  MODIFIED  {} ({} hunk(s))'.format(rel, n_real))

    out = Path(args.report)
    out.write_text(build_report(results, old_root, new_root), encoding='utf-8')
    print('Report written: {}'.format(out.resolve()))

    # exit code 1 when real differences exist (CI gate)
    return 1 if counts['real-change'] or counts['added'] or counts['deleted'] else 0


if __name__ == '__main__':
    sys.exit(main())
