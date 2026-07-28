"""Rows for the viewer's quick-changes panel: pure logic, NO Qt import.

This is the AUTOSAR-level rollup ``--arxml-only`` gives -- port interfaces,
software components, ports, runnables, events, RTE access points, A2L objects
added / removed / changed -- so the reviewer can see the shape of the change
without opening a report. (The list of updated files it once led with is left
out here: the folder tree above already lists every changed file, so it was a
redundant restatement.)

Kept Qt-free so it can be unit tested headless; the widget in summary.py only
walks the returned sections and paints them.
"""

from collections import namedtuple

from ..scanner import (summarize_a2l, summarize_ifaces, summarize_rte,
                       summarize_swcs)

# sign: '+' added, '−' removed, '~' changed. rel = file to jump to, key = the
# name as it is spelled IN that file, so activating a row can land on the hunk
# that mentions it. `name` is the display form and is not always the same
# string: a port shows as 'Ctrl.In2' but the file only ever says 'In2'.
Row = namedtuple('Row', 'sign name detail rel key')


def _iface_kind(tag):
    return tag.replace('-INTERFACE', '')


def _short(path):
    """'/Interfaces/If_Torque' -> 'If_Torque', the SHORT-NAME in the file."""
    return path.rsplit('/', 1)[-1]


def _item(swc, name):
    """'/Comp/Ctrl', 'In2' -> 'Ctrl.In2' (short SWC name keeps rows compact)."""
    return '{}.{}'.format(_short(swc), name)


def summary_sections(results):
    """[(title, [Row, ...]), ...] -- only non-empty sections, in report order."""
    sections = []

    added, removed = summarize_ifaces(results)
    rows = [Row('+', p, _iface_kind(t), rel, _short(p)) for rel, p, t in added]
    rows += [Row('−', p, _iface_kind(t), rel, _short(p)) for rel, p, t in removed]
    if rows:
        sections.append(('Port interfaces', rows))

    swcs = summarize_swcs(results)
    rows = [Row('+', s, '', rel, _short(s)) for rel, s in swcs['swcs']['added']]
    rows += [Row('−', s, '', rel, _short(s)) for rel, s in swcs['swcs']['removed']]
    if rows:
        sections.append(('Software components', rows))

    for cat, title in (('ports', 'Ports'), ('runnables', 'Runnables'),
                       ('events', 'Events')):
        rows = [Row('+', _item(s, n), d, rel, n) for rel, s, n, d in swcs[cat]['added']]
        rows += [Row('−', _item(s, n), d, rel, n) for rel, s, n, d in swcs[cat]['removed']]
        rows += [Row('~', _item(s, n), '{} → {}'.format(od, nd) if od != nd else nd,
                     rel, n)
                 for rel, s, n, od, nd in swcs[cat]['changed']]
        if rows:
            sections.append((title, rows))

    added, removed = summarize_rte(results)
    rows = [Row('+', n, '', rel, n) for rel, n in added]
    rows += [Row('−', n, '', rel, n) for rel, n in removed]
    if rows:
        sections.append(('RTE access points', rows))

    added, removed = summarize_a2l(results)
    rows = [Row('+', n, k, rel, n) for rel, n, k in added]
    rows += [Row('−', n, k, rel, n) for rel, n, k in removed]
    if rows:
        sections.append(('A2L characteristics / measurements', rows))

    return sections
