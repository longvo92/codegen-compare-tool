"""CLI entry point.

Usage:
    python -m compare_tool <old_dir> <new_dir> [--report out.html] [--arxml-only]
    python -m compare_tool                     # side-by-side viewer
"""

import argparse
import sys
from pathlib import Path

from .diff_engine import RULES
from .report import build_arxml_report, build_report
from .scanner import (scan, summarize, summarize_a2l, summarize_ifaces,
                      summarize_rte, summarize_swcs)


def default_report_name(arxml_only):
    return 'arxml_update.html' if arxml_only else 'compare_report.html'


def run_compare(old_root, new_root, out, arxml_only=False, exclude=(),
                progress=None):
    """Scan two trees and write the HTML report.
    Returns (results, counts)."""
    out = Path(out)
    # delete a leftover report from an earlier run BEFORE scanning: if this
    # run dies, a stale report must not pass for this run's result
    if out.exists():
        out.unlink()
    include = tuple('*' + ext for ext, rs in RULES.items()
                    if rs in ('arxml', 'a2l')) if arxml_only else ()
    results = scan(old_root, new_root, progress=progress, exclude=exclude,
                   include=include)
    counts = summarize(results)
    if arxml_only:
        # ALWAYS written: "no changes" must be an explicit statement, never
        # a silently absent file (indistinguishable from a run that died)
        page = build_arxml_report(results, old_root, new_root)
    else:
        page = build_report(results, old_root, new_root)
    out.write_text(page, encoding='utf-8')
    return results, counts


def summary_lines(results, counts):
    """Scan summary as plain-text lines the CLI prints: counts, uncompared
    paths, modified files and the AUTOSAR/A2L semantic rollups."""
    lines = []
    lines.append('Summary: {real-change} modified, {comment-only} comment-only, '
                 '{ignorable-only} unimportant, {added} added, {deleted} deleted, '
                 '{identical} identical, {error} error(s)'.format(**counts))
    if counts['error']:
        lines.append('!! COMPARE INCOMPLETE: {} path(s) could NOT be compared -- '
                     'treat them as potentially changed:'.format(counts['error']))
        for rel, r in sorted(results.items()):
            if r['status'] == 'error':
                for note in r['notes']:
                    lines.append('  !! {} -- {}'.format(rel, note))
    for rel, r in sorted(results.items()):
        if r['status'] == 'real-change':
            n_real = sum(1 for h in r['hunks'] if h['kind'] == 'real')
            if 'binary' in r['notes']:
                n_real = 1
            n_moved = sum(1 for h in r['hunks'] if h['kind'] == 'moved')
            lines.append('  MODIFIED  {} ({} hunk(s){})'.format(
                rel, n_real, ', {} moved'.format(n_moved) if n_moved else ''))

    if_added, if_removed = summarize_ifaces(results)
    if if_added or if_removed:
        lines.append('ARXML interfaces: {} added, {} removed'.format(
            len(if_added), len(if_removed)))
        for rel, p, tag in if_added:
            lines.append('  + {} ({}) in {}'.format(p, tag.replace('-INTERFACE', ''), rel))
        for rel, p, tag in if_removed:
            lines.append('  - {} ({}) in {}'.format(p, tag.replace('-INTERFACE', ''), rel))
    elif any('ifaces' in r for r in results.values()):
        lines.append('ARXML interfaces: none added or removed')

    def item(swc, name):
        return '{}.{}'.format(swc.rsplit('/', 1)[-1], name)

    swc_sum = summarize_swcs(results)
    behavior = []
    for rel, s in swc_sum['swcs']['added']:
        behavior.append('  + SWC {} in {}'.format(s, rel))
    for rel, s in swc_sum['swcs']['removed']:
        behavior.append('  - SWC {} in {}'.format(s, rel))
    for cat, label in (('ports', 'port'), ('runnables', 'runnable'),
                       ('events', 'event')):
        for rel, s, n, d in swc_sum[cat]['added']:
            behavior.append('  + {} {}{} in {}'.format(
                label, item(s, n), ' ({})'.format(d) if d else '', rel))
        for rel, s, n, d in swc_sum[cat]['removed']:
            behavior.append('  - {} {}{} in {}'.format(
                label, item(s, n), ' ({})'.format(d) if d else '', rel))
        for rel, s, n, od, nd in swc_sum[cat]['changed']:
            behavior.append('  ~ {} {} ({} -> {}) in {}'.format(
                label, item(s, n), od, nd, rel))
    if behavior:
        lines.append('AUTOSAR behavior: {} change(s)'.format(len(behavior)))
        lines.extend(behavior)

    rte_added, rte_removed = summarize_rte(results)
    if rte_added or rte_removed:
        lines.append('RTE access points: {} added, {} removed'.format(
            len(rte_added), len(rte_removed)))
        for rel, n in rte_added:
            lines.append('  + {} in {}'.format(n, rel))
        for rel, n in rte_removed:
            lines.append('  - {} in {}'.format(n, rel))

    a2l_added, a2l_removed = summarize_a2l(results)
    if a2l_added or a2l_removed:
        lines.append('A2L objects: {} added, {} removed'.format(
            len(a2l_added), len(a2l_removed)))
        for rel, n, kind in a2l_added:
            lines.append('  + {} ({}) in {}'.format(n, kind, rel))
        for rel, n, kind in a2l_removed:
            lines.append('  - {} ({}) in {}'.format(n, kind, rel))
    return lines


def _parser():
    ap = argparse.ArgumentParser(
        prog='compare_tool',
        description='Compare two AUTOSAR codegen folders, filtering MATLAB noise '
                    '(comments, 1-1 renames, UUIDs, timestamps, whitespace). '
                    'With both folders given it writes a self-contained HTML '
                    'report; without them it opens the side-by-side viewer.')
    ap.add_argument('old_dir', nargs='?', default=None,
                    help='previous codegen output folder')
    ap.add_argument('new_dir', nargs='?', default=None,
                    help='new codegen output folder')
    ap.add_argument('--qt', '--viewer', dest='qt', action='store_true',
                    help='open the side-by-side compare viewer (PySide6): a '
                         'folder tree with a two-pane old/new diff, like Beyond '
                         'Compare. This is also what runs when no folders are '
                         'given, so the flag is only needed to view folders '
                         'passed on the command line instead of comparing them '
                         'in the terminal')
    ap.add_argument('--report', metavar='OUT.html', default=None,
                    help='HTML report output path (default: compare_report.html, '
                         'or arxml_update.html with --arxml-only)')
    ap.add_argument('--arxml-only', action='store_true',
                    help='compare only ARXML/XML and A2L files and write a '
                         'compact "what changed in the AUTOSAR model and '
                         'calibration surface" report instead of the full '
                         'diff report; the report is ALWAYS written -- when '
                         'nothing real changed it states "no changes" '
                         'explicitly per file type')
    ap.add_argument('--exclude', metavar='PATTERN', action='append', default=[],
                    help='skip files matching this glob (relative path or bare '
                         'file name); repeatable. Example: --exclude compare_report.html')
    ap.add_argument('--exit-zero', action='store_true',
                    help='always exit 0 even when real changes exist '
                         '(report-only mode for CI pipelines); compare '
                         'errors still exit 2 -- an incomplete compare '
                         'must never look green')
    return ap


def _wants_viewer(args):
    """The viewer is the default front end: the terminal compare runs only
    when both folders are named on the command line."""
    return bool(args.qt or not (args.old_dir and args.new_dir))


def viewer_requested(argv):
    """Whether this argv opens the viewer, decided WITHOUT running the compare.

    The frozen entry point calls it to hide the console window before Qt comes
    up, so that decision and :func:`main`'s use exactly one rule.
    """
    argv = list(argv)
    if any(a in ('-h', '--help') for a in argv):
        return False  # the help text belongs on a console the user can read
    try:
        return _wants_viewer(_parser().parse_args(argv))
    except SystemExit:
        return False  # bad usage: keep the console, argparse prints there


def main(argv=None):
    ap = _parser()
    args = ap.parse_args(argv)
    if _wants_viewer(args):
        from .qtviewer import run_viewer  # deferred: PySide6 may be absent
        try:
            return run_viewer(args.old_dir, args.new_dir, exclude=args.exclude,
                              arxml_only=args.arxml_only)
        except ImportError as e:
            # a stdlib-only install (the .pyz, a locked-down box) has no Qt.
            # Say so plainly instead of dumping a traceback.
            ap.error('the side-by-side viewer needs PySide6 -- install it with '
                     'pip install "codegen-compare-tool[viewer]", or name both '
                     'folders to compare them in the terminal instead ({})'
                     .format(e))
    # Windows consoles often run a legacy codepage (cp1252/cp437) that cannot
    # encode every character in codegen identifiers/paths; a print must never
    # kill the run, so degrade unencodable characters instead of raising
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')
    if args.report is None:
        args.report = default_report_name(args.arxml_only)

    old_root = Path(args.old_dir)
    new_root = Path(args.new_dir)
    for p, name in ((old_root, 'old_dir'), (new_root, 'new_dir')):
        if not p.is_dir():
            ap.error('{} is not a directory: {}'.format(name, p))

    out = Path(args.report)
    print('Scanning...')

    def progress(done, total, rel):
        if done % 50 == 0 or done == total:
            print('  {}/{} {}'.format(done, total, rel))

    results, counts = run_compare(old_root, new_root, out, args.arxml_only,
                                  exclude=args.exclude, progress=progress)
    for line in summary_lines(results, counts):
        print(line)

    if args.arxml_only:
        if counts['real-change'] or counts['added'] or counts['deleted']:
            print('ARXML/A2L update report written: {}'.format(out.resolve()))
        elif counts['error']:
            print('ARXML/A2L compare incomplete -- report written: {}'
                  .format(out.resolve()))
        else:
            print('No ARXML/A2L changes -- report written: {}'.format(out.resolve()))
    else:
        print('Report written: {}'.format(out.resolve()))

    if counts['error']:
        # fail-safe: an incomplete compare must never look green, even with
        # --exit-zero -- an uncompared file could hide a real change
        return 2
    if args.exit_zero:
        return 0
    # exit code 1 when real differences exist (CI gate)
    return 1 if counts['real-change'] or counts['added'] or counts['deleted'] else 0


if __name__ == '__main__':
    sys.exit(main())
