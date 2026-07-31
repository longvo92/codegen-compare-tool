"""Preconditions for a release, and the release notes that go with it.

The release workflow runs this before it builds anything, and it is meant to be
run by hand (or by an agent) BEFORE triggering that workflow -- same script,
same answer, so a release never fails halfway through for a reason that could
have been found in a second.

    python packaging/release_check.py 1.3.1
    python packaging/release_check.py 1.3.1 --notes notes.md

Every failure prints what is wrong and what to change, because the reader is
usually a log or an agent, not somebody with the repo open.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / 'compare_tool' / '__init__.py'
CHANGELOG = ROOT / 'CHANGELOG.md'


def declared_version():
    """The version in compare_tool/__init__.py, read as text rather than
    imported: this runs before anything is installed."""
    m = re.search(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]',
                  INIT.read_text(encoding='utf-8'), re.M)
    if not m:
        raise SystemExit('{}: no __version__ found'.format(INIT))
    return m.group(1)


def changelog_section(version):
    """(body, heading) for `## [version]`, or (None, None) when absent."""
    text = CHANGELOG.read_text(encoding='utf-8')
    heads = list(re.finditer(r'^## \[([^\]]+)\].*$', text, re.M))
    for i, h in enumerate(heads):
        if h.group(1) == version:
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            return text[h.end():end].strip(), h.group(0)
    return None, None


def problems(version):
    """Every reason this version is not ready, as a list of sentences. Empty
    list means go."""
    out = []
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        out.append('version {!r} is not X.Y.Z'.format(version))

    declared = declared_version()
    if declared != version:
        out.append('compare_tool/__init__.py says __version__ = {!r}, not {!r} '
                   '-- bump it and merge that first'.format(declared, version))

    body, _heading = changelog_section(version)
    if body is None:
        out.append('CHANGELOG.md has no "## [{}]" section -- move the '
                   '[Unreleased] entries under it, with the date'.format(version))
    elif not body:
        out.append('the "## [{}]" section in CHANGELOG.md is empty'.format(version))

    unreleased, _ = changelog_section('Unreleased')
    if unreleased:
        out.append('CHANGELOG.md still has entries under [Unreleased]; they '
                   'would ship without being listed in the release notes')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('version', help='the version being released, e.g. 1.3.1')
    p.add_argument('--notes', help='write the CHANGELOG section to this file')
    args = p.parse_args(argv)

    found = problems(args.version)
    if found:
        print('Not ready to release {}:'.format(args.version), file=sys.stderr)
        for line in found:
            print('  - {}'.format(line), file=sys.stderr)
        return 1

    body, _ = changelog_section(args.version)
    if args.notes:
        Path(args.notes).write_text(body + '\n', encoding='utf-8')
    print('{} is ready: version and CHANGELOG agree, [Unreleased] is '
          'empty.'.format(args.version))
    return 0


if __name__ == '__main__':
    sys.exit(main())
