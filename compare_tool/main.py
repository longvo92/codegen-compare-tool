"""CLI entry point.

Usage:
    python -m compare_tool <old_dir> <new_dir> [--report out.html]
"""

import argparse
import sys
from pathlib import Path

from .report import build_report
from .scanner import (scan, summarize, summarize_ifaces, summarize_rte,
                      summarize_swcs)


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
    ap.add_argument('--exclude', metavar='PATTERN', action='append', default=[],
                    help='skip files matching this glob (relative path or bare '
                         'file name); repeatable. Example: --exclude compare_report.html')
    ap.add_argument('--exit-zero', action='store_true',
                    help='always exit 0 even when real changes exist '
                         '(report-only mode for CI pipelines)')
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

    results = scan(old_root, new_root, progress=progress, exclude=args.exclude)
    counts = summarize(results)
    print('Summary: {real-change} modified, {ignorable-only} unimportant, '
          '{added} added, {deleted} deleted, {identical} identical'.format(**counts))
    for rel, r in sorted(results.items()):
        if r['status'] == 'real-change':
            n_real = sum(1 for h in r['hunks'] if h['kind'] == 'real')
            if 'binary' in r['notes']:
                n_real = 1
            n_moved = sum(1 for h in r['hunks'] if h['kind'] == 'moved')
            print('  MODIFIED  {} ({} hunk(s){})'.format(
                rel, n_real, ', {} moved'.format(n_moved) if n_moved else ''))

    if_added, if_removed = summarize_ifaces(results)
    if if_added or if_removed:
        print('ARXML interfaces: {} added, {} removed'.format(
            len(if_added), len(if_removed)))
        for rel, p, tag in if_added:
            print('  + {} ({}) in {}'.format(p, tag.replace('-INTERFACE', ''), rel))
        for rel, p, tag in if_removed:
            print('  - {} ({}) in {}'.format(p, tag.replace('-INTERFACE', ''), rel))
    elif any('ifaces' in r for r in results.values()):
        print('ARXML interfaces: none added or removed')

    def item(swc, name):
        return '{}.{}'.format(swc.rsplit('/', 1)[-1], name)

    swc_sum = summarize_swcs(results)
    lines = []
    for rel, s in swc_sum['swcs']['added']:
        lines.append('  + SWC {} in {}'.format(s, rel))
    for rel, s in swc_sum['swcs']['removed']:
        lines.append('  - SWC {} in {}'.format(s, rel))
    for cat, label in (('ports', 'port'), ('runnables', 'runnable'),
                       ('events', 'event')):
        for rel, s, n, d in swc_sum[cat]['added']:
            lines.append('  + {} {}{} in {}'.format(
                label, item(s, n), ' ({})'.format(d) if d else '', rel))
        for rel, s, n, d in swc_sum[cat]['removed']:
            lines.append('  - {} {}{} in {}'.format(
                label, item(s, n), ' ({})'.format(d) if d else '', rel))
        for rel, s, n, od, nd in swc_sum[cat]['changed']:
            lines.append('  ~ {} {} ({} -> {}) in {}'.format(
                label, item(s, n), od, nd, rel))
    if lines:
        print('AUTOSAR behavior: {} change(s)'.format(len(lines)))
        for line in lines:
            print(line)

    rte_added, rte_removed = summarize_rte(results)
    if rte_added or rte_removed:
        print('RTE access points: {} added, {} removed'.format(
            len(rte_added), len(rte_removed)))
        for rel, n in rte_added:
            print('  + {} in {}'.format(n, rel))
        for rel, n in rte_removed:
            print('  - {} in {}'.format(n, rel))

    out = Path(args.report)
    out.write_text(build_report(results, old_root, new_root), encoding='utf-8')
    print('Report written: {}'.format(out.resolve()))

    if args.exit_zero:
        return 0
    # exit code 1 when real differences exist (CI gate)
    return 1 if counts['real-change'] or counts['added'] or counts['deleted'] else 0


if __name__ == '__main__':
    sys.exit(main())
