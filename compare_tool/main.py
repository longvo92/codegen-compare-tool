"""CLI entry point.

Usage:
    python -m compare_tool <old_dir> <new_dir> [--report out.html] [--arxml-only]
    python -m compare_tool [--theme light]     # side-by-side viewer

Either folder argument may be a ``.zip`` (an Azure DevOps build artifact, say):
it is unpacked read-only into a temp directory and compared as if it had always
been a folder, then the temp directory is removed on exit.
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from . import review, theme, zipsource
from .diff_engine import RULES
from .report import build_arxml_report, build_report
from .view_model import SWC_DISPLAY, iface_kind, swc_item
from .scanner import (scan, summarize, summarize_a2l, summarize_ifaces,
                      summarize_rte, summarize_swcs)


class ReportWriteError(Exception):
    """The report path could not be written, so this run left no record.

    Carries the scan it could not write (``results`` / ``counts``, None when
    the failure came before the scan) so the caller can still print what was
    found instead of throwing the whole run away.
    """

    def __init__(self, message, results=None, counts=None):
        super().__init__(message)
        self.results = results
        self.counts = counts


def _write_hint(out, err):
    """Why a report path could not be written, in the reviewer's terms rather
    than as a traceback: the two everyday causes are a folder that does not
    exist and a report still open in a browser holding the file."""
    reason = err.strerror or str(err)
    if not out.parent.is_dir():
        reason += ' -- the folder {} does not exist'.format(out.parent)
    elif isinstance(err, PermissionError):
        reason += ' -- the file may be open in a browser or editor, or read-only'
    return '{}: {}'.format(out, reason)


def default_report_name(arxml_only):
    return 'arxml_update.html' if arxml_only else 'compare_report.html'


def run_compare(old_root, new_root, out, arxml_only=False, exclude=(),
                progress=None, reviews=None, theme_name=theme.DEFAULT,
                old_label=None, new_label=None):
    """Scan two trees and write the HTML report.

    ``old_label`` / ``new_label`` name the two sides in the report header when
    their folder names do not (``--baseline-name`` / ``--current-name``).

    Returns (results, counts). Raises :class:`ReportWriteError` when the report
    could not be written -- a run whose record does not exist is not a run that
    may report success."""
    out = Path(out)
    # delete a leftover report from an earlier run BEFORE scanning: if this
    # run dies, a stale report must not pass for this run's result
    try:
        if out.exists():
            out.unlink()
    # `from None` here and below: _write_hint already folds the OSError into a
    # sentence, and the caller prints that sentence and exits 2 -- the chained
    # cause would only add a traceback to an error that is handled
    except OSError as e:
        raise ReportWriteError(_write_hint(out, e)) from None
    include = tuple('*' + ext for ext, rs in RULES.items()
                    if rs in ('arxml', 'a2l')) if arxml_only else ()
    results = scan(old_root, new_root, progress=progress, exclude=exclude,
                   include=include)
    counts = summarize(results)
    if arxml_only:
        # ALWAYS written: "no changes" must be an explicit statement, never
        # a silently absent file (indistinguishable from a run that died)
        page = build_arxml_report(results, old_root, new_root,
                                  old_label=old_label, theme_name=theme_name,
                                  new_label=new_label)
    else:
        page = build_report(results, old_root, new_root, reviews,
                            old_label=old_label, theme_name=theme_name,
                            new_label=new_label)
    try:
        out.write_text(page, encoding='utf-8')
    except OSError as e:
        raise ReportWriteError(_write_hint(out, e), results, counts) from None
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
            lines.append('  + {} ({}) in {}'.format(p, iface_kind(tag), rel))
        for rel, p, tag in if_removed:
            lines.append('  - {} ({}) in {}'.format(p, iface_kind(tag), rel))
    elif any('ifaces' in r for r in results.values()):
        lines.append('ARXML interfaces: none added or removed')

    swc_sum = summarize_swcs(results)
    behavior = []
    for rel, s in swc_sum['swcs']['added']:
        behavior.append('  + SWC {} in {}'.format(s, rel))
    for rel, s in swc_sum['swcs']['removed']:
        behavior.append('  - SWC {} in {}'.format(s, rel))
    for cat in SWC_DISPLAY:
        for rel, s, n, d in swc_sum[cat.key]['added']:
            behavior.append('  + {} {}{} in {}'.format(
                cat.noun, swc_item(s, n), ' ({})'.format(d) if d else '', rel))
        for rel, s, n, d in swc_sum[cat.key]['removed']:
            behavior.append('  - {} {}{} in {}'.format(
                cat.noun, swc_item(s, n), ' ({})'.format(d) if d else '', rel))
        for rel, s, n, od, nd in swc_sum[cat.key]['changed']:
            behavior.append('  ~ {} {} ({} -> {}) in {}'.format(
                cat.noun, swc_item(s, n), od, nd, rel))
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
                         'folder tree with a two-pane BASELINE/CURRENT diff. '
                         'This is also what runs when no folders are given, so '
                         'the flag is only needed to view folders passed on the '
                         'command line instead of comparing them in the terminal')
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
    # A pipeline stages the baseline into a fixed scratch directory, so the
    # header ends up naming the mechanism (`cg_temp`) instead of what was
    # compared. The folder path stays in the tooltip either way -- these rename
    # a side in the report, they never stand in for one.
    ap.add_argument('--baseline-name', metavar='NAME', default=None,
                    help='name the BASELINE side in the report header instead '
                         'of using its folder name -- for a pipeline that '
                         'stages the previous codegen into a scratch directory, '
                         'where the folder name says nothing. Example: '
                         '--baseline-name "build 4821"')
    ap.add_argument('--current-name', metavar='NAME', default=None,
                    help='same for the CURRENT side')
    ap.add_argument('--theme', choices=theme.THEMES, default=theme.DEFAULT,
                    help='colour scheme the viewer opens with, and the one the '
                         'HTML report opens with (default: dark). The report '
                         'always carries both, so its own button switches with '
                         'nothing to download; the viewer has the same button '
                         'in its toolbar')
    ap.add_argument('--exclude', metavar='PATTERN', action='append', default=[],
                    help='skip files matching this glob (relative path or bare '
                         'file name); repeatable. Example: --exclude compare_report.html')
    ap.add_argument('--review', metavar='REVIEW.json', default=None,
                    help='review file written by the viewer (default name: '
                         'codegen-review.json). Its notes are rendered next to '
                         'the changes they belong to and the report gains a '
                         'Reviewed badge that hides the changes already signed '
                         'off. Not loaded unless named: a report must not pick '
                         'up someone else\'s sign-off by accident')
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


def _resolve_source(ap, arg, zip_temp):
    """A folder argument that may be a ``.zip``. Returns ``(root, label)``.

    A zip is unpacked read-only into a shared temp directory (created lazily,
    boxed in ``zip_temp`` so the caller can clean it up) and labelled by its
    file name -- the temp path names nothing a reviewer would recognise. A zip
    that cannot be read is loud and fatal, never a silent empty folder.
    """
    p = Path(arg)
    if not zipsource.is_zip(p):
        return p, None
    if zip_temp[0] is None:
        zip_temp[0] = tempfile.mkdtemp(prefix='codegen-compare-zip-')
    try:
        return zipsource.extract(p, zip_temp[0]), p.name
    except zipsource.ZipError as e:
        ap.error('cannot use {} as a compare source: {}'.format(arg, e))


def _viewer_source(ap, arg, zip_temp):
    """A viewer folder argument as a path string, a ``.zip`` unpacked first.
    ``None`` (no folder given) is passed straight through."""
    if not arg:
        return arg
    return str(_resolve_source(ap, arg, zip_temp)[0])


def main(argv=None):
    ap = _parser()
    args = ap.parse_args(argv)
    # boxed so _resolve_source can create the extraction dir lazily; removed in
    # the finally whichever way this run exits
    zip_temp = [None]
    try:
        return _run(ap, args, zip_temp)
    finally:
        if zip_temp[0]:
            shutil.rmtree(zip_temp[0], ignore_errors=True)


def _run(ap, args, zip_temp):
    if _wants_viewer(args):
        from .qtviewer import run_viewer  # deferred: PySide6 may be absent
        old_dir = _viewer_source(ap, args.old_dir, zip_temp)
        new_dir = _viewer_source(ap, args.new_dir, zip_temp)
        try:
            return run_viewer(old_dir, new_dir, exclude=args.exclude,
                              arxml_only=args.arxml_only, theme_name=args.theme)
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

    old_root, old_zip = _resolve_source(ap, args.old_dir, zip_temp)
    new_root, new_zip = _resolve_source(ap, args.new_dir, zip_temp)
    for p, name in ((old_root, 'old_dir'), (new_root, 'new_dir')):
        if not p.is_dir():
            ap.error('{} is not a directory: {}'.format(name, p))

    reviews = None
    if args.review:
        reviews = review.ReviewStore.load(args.review)
        if reviews.error:
            # loud, not fatal: an unread review file leaves every change
            # counting as not reviewed, so the report still shows everything
            print('!! review file NOT read: {} -- {}'.format(
                reviews.path, reviews.error), file=sys.stderr)
        if args.arxml_only:
            print('note: --review has no effect with --arxml-only (that report '
                  'lists files, not individual changes)', file=sys.stderr)

    out = Path(args.report)
    print('Scanning...')

    def progress(done, total, rel):
        if done % 50 == 0 or done == total:
            print('  {}/{} {}'.format(done, total, rel))

    try:
        results, counts = run_compare(old_root, new_root, out, args.arxml_only,
                                      exclude=args.exclude, progress=progress,
                                      reviews=reviews, theme_name=args.theme,
                                      old_label=args.baseline_name or old_zip,
                                      new_label=args.current_name or new_zip)
    except ReportWriteError as e:
        # what WAS scanned still goes to the terminal -- the compare itself may
        # have been fine, it is only the record that is missing
        if e.results is not None:
            for line in summary_lines(e.results, e.counts):
                print(line)
        print('!! REPORT NOT WRITTEN -- {}'.format(e), file=sys.stderr)
        print('!! This run left no record: treat it as INCOMPLETE.',
              file=sys.stderr)
        # exit 2, never 1: 1 is the gate's "real changes found", a perfectly
        # normal outcome, and a run that produced no report must not be
        # indistinguishable from it (--exit-zero cannot mask this either)
        return 2
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
