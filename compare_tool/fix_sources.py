"""Locate the two inputs of an ARXML repair without asking for them.

Simulink AUTOSAR code generation always lays its output out the same way::

    <codegen>/<Model>_autosar_rtw/<Model>.c, <Model>_component.arxml, ...
    <codegen>/<Dictionary>/<Dictionary>_interface.arxml, stub/..._external_interface.arxml
    <codegen>/<Architecture>/   a full export of every ARXML (never used here)

and every generated file carries a stamp: the model, its *Model version* and
the time it was generated. A delivery (the CURRENT tree Code Check reads)
holds the generated C and a folder of ARXML -- the Master to patch -- but not
the freshly generated ARXML. That one is found here, by the folder layout, and
accepted only when its Model version is exactly the version stamped in the C
of the same model. Anything that cannot be proven is reported, never guessed.

Standard library only; nothing here writes to the inputs.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import consistency, naming
from .messages import Message
from .scanner import SKIP_DIRS, list_files

RTW_SUFFIX = '_autosar_rtw'
HEADER_BYTES = 2048
SEARCH_PARENTS = 3        # CURRENT, then up to this many parent folders
SEARCH_DEPTH = 3          # folder levels below each starting point
SEARCH_LIMIT = 3000       # folders visited in one automatic search
DICTIONARY_DEPTH = 2      # <Dictionary>/stub/*.arxml
_SKIP = {name.lower() for name in SKIP_DIRS} | {'slprj', 'node_modules'}

_C_MODEL = re.compile(r"Code generated for Simulink model '([^'\r\n]+)'")
_ARXML_MODEL = re.compile(r'for model\s+([^\s<>]+)')
_VERSION = re.compile(r'^[\s*/#!-]*Model version\s*:\s*(\S+)', re.MULTILINE)
_GENERATED = re.compile(r'source code generated on\s*:\s*([^\r\n]+)')
_MONTHS = {name: i for i, name in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), 1)}


@dataclass(frozen=True)
class Stamp:
    """What a generated file says about itself. ``None`` fields were absent."""
    path: Path
    model: Optional[str] = None
    version: Optional[str] = None
    generated: Optional[datetime] = None
    error: str = ''


def parse_date(text):
    """'Tue Nov  3 22:34:33 2026' or 'Wed Nov 04 21:59:32 2026' -> datetime.

    Parsed with a fixed English month table rather than strptime, whose %a/%b
    follow the machine's locale. None when the text is not such a date."""
    parts = text.split()
    if len(parts) < 4:
        return None
    if parts[0][:3].lower() in {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}:
        parts = parts[1:]
    try:
        month = _MONTHS[parts[0][:3].lower()]
        day, clock, year = int(parts[1]), parts[2], int(parts[3])
        hour, minute, second = (int(x) for x in clock.split(':'))
        return datetime(year, month, day, hour, minute, second)
    except (KeyError, ValueError, IndexError):
        return None


def read_stamp(path):
    """The generation stamp in the first bytes of a generated C or ARXML file."""
    path = Path(path)
    try:
        with open(path, 'rb') as handle:
            head = handle.read(HEADER_BYTES).decode('utf-8', errors='replace')
    except OSError as exc:
        return Stamp(path, error=str(exc))
    model = _C_MODEL.search(head) or _ARXML_MODEL.search(head)
    version = _VERSION.search(head)
    generated = _GENERATED.search(head)
    return Stamp(path, model.group(1) if model else None, version.group(1) if version else None,
                 parse_date(generated.group(1)) if generated else None)


def _when(stamp_time):
    return stamp_time.strftime('%Y-%m-%d %H:%M:%S') if stamp_time else '?'


@dataclass(eq=False)
class ModelSource:
    """The generated ARXML chosen for one model, or why none could be."""
    model: str
    c_file: str
    c_version: Optional[str] = None
    folder: Optional[Path] = None
    files: tuple = ()
    arxml_version: Optional[str] = None
    arxml_generated: Optional[datetime] = None
    problem: Optional[Message] = None


@dataclass(eq=False)
class FixSources:
    """Master and staged Source for one Code Check result.

    ``staged`` is a temporary copy of the chosen generated ARXML; it must stay
    on disk until any write that uses it has finished. ``close`` removes it --
    the description stays readable afterwards."""
    root: Path
    master: Optional[Path] = None
    search: str = 'auto'
    codegen_roots: tuple = ()
    visited: int = 0
    models: dict = field(default_factory=dict)
    finding_models: dict = field(default_factory=dict)
    dictionary: tuple = ()
    staged: Optional[Path] = None
    problem: Optional[Message] = None
    notes: list = field(default_factory=list)
    _finalizer: Any = None

    def ok_models(self):
        return [m for m in self.models.values() if m.problem is None and m.files]

    def messages(self):
        """Per-finding explanations: the problem of the finding's model."""
        out = {}
        for key, model in self.finding_models.items():
            source = self.models.get(model)
            if source is not None and source.problem is not None:
                out[key] = source.problem
        return out

    def close(self):
        if self._finalizer is not None:
            self._finalizer()
            self._finalizer = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def problems(self):
        """Only the reasons nothing could be used, for a caller that does not
        list the inputs themselves."""
        out = [self.problem] if self.problem is not None else []
        out += [Message('Model {}: {}', s.model, s.problem)
                for s in sorted(self.models.values(), key=lambda s: s.model) if s.problem is not None]
        return out

    def lines(self):
        """The full description, printed by the CLI."""
        out = []
        if self.problem is not None:
            out.append(self.problem)
        if self.master is not None:
            out.append(Message('Master: {}', self.master))
        for source in sorted(self.models.values(), key=lambda s: s.model):
            if source.problem is None and source.files:
                out.append(Message('Source: model {} {}, generated {}: {}', source.model,
                                   source.arxml_version, _when(source.arxml_generated), source.folder))
            elif source.problem is not None:
                out.append(Message('Model {}: {}', source.model, source.problem))
        if self.dictionary:
            out.append(Message('Shared ARXML: {}', ', '.join(sorted(p.name for p in self.dictionary))))
        if self.search == 'settings':
            for root in self.codegen_roots:
                out.append(Message('Codegen output: {} (Settings)', root))
        else:
            out.append(Message('Codegen output: {} (searched {} folders around CURRENT)',
                               ', '.join(str(r) for r in self.codegen_roots) or '-', self.visited))
        out.extend(self.notes)
        return out


# --- discovery ------------------------------------------------------------------

class UnreadableFolder(OSError):
    """A folder the search had to read and could not. Never an empty folder:
    a generated set behind it would otherwise look absent."""

    def __init__(self, path, exc):
        super().__init__('{}: {}'.format(path, exc))
        self.path = Path(path)
        self.reason = str(exc)


def _is_link(path):
    try:
        if path.is_symlink():
            return True
        isjunction = getattr(os.path, 'isjunction', None)
        return bool(isjunction and isjunction(path))
    except OSError:
        return True


def _subdirs(folder):
    try:
        entries = list(os.scandir(folder))
    except OSError as exc:
        raise UnreadableFolder(folder, exc) from exc
    out = []
    for entry in sorted(entries, key=lambda e: e.name.lower()):
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError as exc:
            raise UnreadableFolder(entry.path, exc) from exc
        name = entry.name
        if name.startswith('.') or name.lower() in _SKIP:
            continue
        path = Path(entry.path)
        if not _is_link(path):
            out.append(path)
    return out


def _arxml_files(folder):
    try:
        return sorted((p for p in Path(folder).iterdir()
                       if p.is_file() and p.suffix.lower() == '.arxml'), key=lambda p: p.name.lower())
    except OSError as exc:
        raise UnreadableFolder(folder, exc) from exc


def _rtw_model(folder):
    """The model of an ``<M>_autosar_rtw`` folder that holds ``<M>_component.arxml``."""
    name = folder.name
    if not name.lower().endswith(RTW_SUFFIX):
        return None
    model = name[:-len(RTW_SUFFIX)]
    wanted = (model + '_component.arxml').lower()
    return model if any(p.name.lower() == wanted for p in _arxml_files(folder)) else None


def _is_codegen_root(folder):
    return any(_rtw_model(child) for child in _subdirs(folder))


def search_codegen_roots(start, parents=SEARCH_PARENTS, depth=SEARCH_DEPTH, limit=SEARCH_LIMIT):
    """Codegen output folders around ``start``: itself, then each parent, each
    walked breadth-first ``depth`` levels down.

    Returns (roots, visited, hit_limit, unreadable). A search that hit its limit
    or could not read a folder is incomplete: the caller must not choose from it."""
    start = Path(start).resolve()
    anchors = [start] + list(start.parents)[:parents]
    seen, roots, visited, unreadable = set(), [], 0, []
    for anchor in anchors:
        frontier = [(anchor, 0)]
        while frontier:
            folder, level = frontier.pop(0)
            key = os.path.normcase(str(folder))
            if key in seen:
                continue
            seen.add(key)
            visited += 1
            if visited > limit:
                return roots, visited - 1, True, unreadable
            try:
                children = _subdirs(folder)
                if any(_rtw_model(child) for child in children):
                    roots.append(folder)
            except UnreadableFolder as exc:
                unreadable.append(exc)
                continue
            if level < depth:
                frontier.extend((child, level + 1) for child in children
                                if not child.name.lower().endswith(RTW_SUFFIX))
    return roots, visited, False, unreadable


# --- choosing the generated ARXML ----------------------------------------------

def _candidate(folder, model):
    """(files, version, generated, problem) for one ``<M>_autosar_rtw`` folder."""
    files = [p for p in _arxml_files(folder) if naming.model_of(naming.stem(p.name), [model])]
    if not files:
        return (), None, None, Message('{} has no ARXML for model {}.', folder, model)
    stamps = [read_stamp(p) for p in files]
    for stamp in stamps:
        if stamp.error:
            return (), None, None, Message('{} could not be read: {}', stamp.path, stamp.error)
        if stamp.model != model or not stamp.version:
            return (), None, None, Message('{} carries no generation stamp for model {}.', stamp.path, model)
    versions = {s.version for s in stamps}
    if len(versions) != 1:
        return (), None, None, Message('{} mixes ARXML of model versions {}.', folder, ', '.join(sorted(versions)))
    times = [s.generated for s in stamps if s.generated]
    return tuple(files), versions.pop(), max(times) if times else None, None


def _same_files(first, second):
    names = sorted(p.name.lower() for p in first)
    if names != sorted(p.name.lower() for p in second):
        return False
    other = {p.name.lower(): p for p in second}
    try:
        return all(p.read_bytes() == other[p.name.lower()].read_bytes() for p in first)
    except OSError:
        return False


def _choose(source, roots):
    rtw = (source.model + RTW_SUFFIX).lower()
    found = []
    for root in roots:
        for child in _subdirs(root):
            if child.name.lower() == rtw:
                files, version, generated, problem = _candidate(child, source.model)
                found.append((child, files, version, generated, problem))
    usable = [c for c in found if c[4] is None]
    if not usable:
        if found:
            source.problem = found[0][4]
        else:
            source.problem = Message('No generated ARXML for model {} in {}.', source.model,
                                     ', '.join(str(r) for r in roots) or '-')
        return
    matching = [c for c in usable if c[2] == source.c_version]
    if not matching:
        source.problem = Message(
            'Generated ARXML for model {} is {}, the code is {}: regenerate the ARXML.',
            source.model, ', '.join(sorted({c[2] for c in usable})), source.c_version)
        return
    matching.sort(key=lambda c: (c[3] is not None, c[3] or datetime.min), reverse=True)
    best = matching[0]
    for other in matching[1:]:
        if other[3] != best[3]:
            break
        if not _same_files(best[1], other[1]):
            source.problem = Message(
                'Several generated ARXML sets for model {} {} share one stamp: {}, {}.',
                source.model, source.c_version, best[0], other[0])
            return
    if best[3] is None and len(matching) > 1:
        source.problem = Message('Several unstamped ARXML sets for model {} {}: {}.', source.model,
                                 source.c_version, ', '.join(str(c[0]) for c in matching))
        return
    source.folder, source.files = best[0], best[1]
    source.arxml_version, source.arxml_generated = best[2], best[3]


def _dictionary(roots, models, chosen):
    """Shared ARXML (interfaces, data types) generated next to the models.

    Folders that hold any model's own ARXML, or a composition, are a full
    architecture export and are skipped: mixing them in would duplicate every
    definition. Files with one name are de-duplicated by their newest stamp."""
    ordered = sorted(models, key=len, reverse=True)
    picked, problem = {}, None
    for root in roots:
        for child in _subdirs(root):
            if child.name.lower().endswith(RTW_SUFFIX):
                continue
            files, frontier = [], [(child, 0)]
            while frontier:
                folder, level = frontier.pop(0)
                files.extend(_arxml_files(folder))
                if level < DICTIONARY_DEPTH - 1:
                    frontier.extend((sub, level + 1) for sub in _subdirs(folder))
            stems = [naming.stem(p.name) for p in files]
            if any(naming.model_of(s, ordered) or s.lower().endswith('_composition') for s in stems):
                continue
            for path in files:
                picked.setdefault(os.path.normcase(path.name), []).append(path)
    for source in chosen:   # an rtw folder can carry shared files too
        for path in _arxml_files(source.folder):
            if not naming.model_of(naming.stem(path.name), ordered):
                picked.setdefault(os.path.normcase(path.name), []).append(path)
    out = []
    for name in sorted(picked):
        paths = picked[name]
        if len(paths) == 1:
            out.append(paths[0])
            continue
        stamped = sorted(((read_stamp(p).generated, p) for p in paths),
                         key=lambda t: (t[0] is not None, t[0] or datetime.min), reverse=True)
        best = stamped[0]
        rivals = [p for when, p in stamped[1:] if when == best[0]]
        try:
            if any(p.read_bytes() != best[1].read_bytes() for p in rivals):
                problem = Message('Shared ARXML {} exists in several versions with one stamp: {}.',
                                  best[1].name, ', '.join(str(p) for p in [best[1]] + rivals))
        except OSError as exc:
            problem = Message('Shared ARXML {} could not be read: {}', best[1].name, exc)
        out.append(best[1])
    return tuple(out), problem


def _stage(files):
    folder = Path(tempfile.mkdtemp(prefix='codegen-fix-source-'))
    written = {}
    try:
        for path in files:
            key = os.path.normcase(path.name)
            if key in written:
                if written[key].read_bytes() != path.read_bytes():
                    raise ValueError('{} and {} share a file name'.format(written[key], path))
                continue
            shutil.copyfile(path, folder / path.name)
            written[key] = path
    except Exception:
        shutil.rmtree(str(folder), ignore_errors=True)
        raise
    return folder


# --- entry point ----------------------------------------------------------------

def detect_fix_sources(root, check, exclude=(), *, codegen_root='', stage=True):
    """Master and generated Source for the repairable findings of ``check``.

    Never raises for an input it cannot use: ``problem`` (everything blocked) or
    a model's ``problem`` (that model's findings blocked) says why."""
    from .fix_suggestions import candidate, finding_key

    root = Path(root).resolve()
    result = FixSources(root)
    targets = [f for f in check.findings if candidate(f)]
    if not targets:
        result.problem = Message('No finding here can be repaired from generated ARXML.')
        return result

    # 1. which models produced the failing calls, and at which version
    for finding in targets:
        rel = finding['call'].file
        stamp = read_stamp(root / rel)
        parent = Path(rel).parent.name
        model = stamp.model or (parent[:-len(RTW_SUFFIX)] if parent.lower().endswith(RTW_SUFFIX) else None)
        if not model:
            model = naming.stem(rel)
        result.finding_models[finding_key(finding)] = model
        source = result.models.get(model)
        if source is None:
            source = result.models[model] = ModelSource(model, rel, stamp.version)
            if stamp.error:
                source.problem = Message('{} could not be read: {}', rel, stamp.error)
            elif not stamp.version:
                source.problem = Message(
                    '{} has no Model version stamp; cannot match generated ARXML for model {}.', rel, model)
        elif source.problem is None and stamp.version != source.c_version:
            source.problem = Message('{} and {} carry different Model versions ({}, {}).',
                                     source.c_file, rel, source.c_version, stamp.version)

    # 2. where the generated ARXML lives
    if codegen_root:
        folder = Path(codegen_root)
        folder = (folder if folder.is_absolute() else root / folder).resolve()
        result.search = 'settings'
        result.codegen_roots = (folder,)
        if not folder.is_dir():
            result.problem = Message('Codegen output folder not found: {}', folder)
            return result
        try:
            if not _is_codegen_root(folder):
                result.problem = Message('{} holds no <Model>_autosar_rtw folder with generated ARXML.', folder)
                return result
        except UnreadableFolder as exc:
            result.problem = Message('{} could not be read: {}', exc.path, exc.reason)
            return result
    else:
        roots, visited, capped, unreadable = search_codegen_roots(root)
        result.codegen_roots, result.visited = tuple(roots), visited
        # an incomplete search can miss a newer set: it never chooses
        if capped:
            result.problem = Message(
                'Auto-search stopped after {} folders; set Settings › Code Check › Codegen output folder.',
                visited)
            return result
        if unreadable:
            result.problem = Message(
                'Auto-search could not read {} ({} folder(s)); set Settings › Code Check › Codegen output folder.',
                unreadable[0].path, len(unreadable))
            return result
        if not roots:
            result.problem = Message('No generated ARXML (<Model>_autosar_rtw) found around CURRENT; '
                                     'set Settings › Code Check › Codegen output folder.')
            return result

    # 3. the Master: the CURRENT folder that defines the failing runnables
    inside = [r for r in result.codegen_roots if r == root or root in r.parents]
    if inside:
        result.notes.append(Message('The codegen output {} is inside CURRENT; Code Check also read it.',
                                    ', '.join(str(r) for r in inside)))
    arxml = []
    for rel in list_files(root):
        if Path(rel).suffix.lower() != '.arxml' or consistency._matches(rel, exclude):
            continue
        # generated ARXML is the Source, never the Master: a codegen output
        # below CURRENT is left out whole; when CURRENT is the codegen output
        # itself, only its model folders are
        path = (root / rel).resolve()
        if any(r != root and r in path.parents for r in inside) or any(
                parent.name.lower().endswith(RTW_SUFFIX) and parent.parent == root
                for parent in path.parents):
            continue
        arxml.append(rel)
    _accesses, runnables, errors, _service, _ports = consistency._parse_arxml(root, sorted(arxml))
    if errors:
        result.problem = Message('CURRENT ARXML could not be read; fix the scan errors first.')
        return result
    folders = set()
    for finding in targets:
        for definition in runnables.get(finding['runnable'], []):
            folders.add(Path(definition.source_file).parent.as_posix())
    if len(folders) != 1:
        result.problem = (
            Message('The failing runnables are defined in several ARXML folders ({}); use the ARXML Handler.',
                    ', '.join(sorted(folders))) if folders else
            Message('The failing runnables have no definition in CURRENT ARXML.'))
        return result
    result.master = (root / folders.pop()).resolve()

    # 4. per model: the generated set whose Model version matches the code
    try:
        for source in result.models.values():
            if source.problem is None:
                _choose(source, result.codegen_roots)
        chosen = result.ok_models()
        if not chosen:
            return result
        known = {child_model for r in result.codegen_roots for child in _subdirs(r)
                 for child_model in [_rtw_model(child)] if child_model}
        known.update(result.models)
        dictionary, problem = _dictionary(
            sorted({s.folder.parent for s in chosen}, key=str), known, chosen)
    except UnreadableFolder as exc:
        for source in result.models.values():
            source.folder, source.files = None, ()
        result.problem = Message('{} could not be read: {}', exc.path, exc.reason)
        return result
    result.dictionary = dictionary
    if problem is not None:
        result.problem = problem
        return result

    # 5. stage a private copy: the patch engine reads Source again before writing
    if stage:
        files = [p for s in chosen for p in s.files] + list(result.dictionary)
        try:
            result.staged = _stage(files)
            # removed by close(), or at the latest when the result is collected
            result._finalizer = weakref.finalize(result, shutil.rmtree, str(result.staged), True)
        except (OSError, ValueError) as exc:
            result.problem = Message('Generated ARXML could not be staged: {}', exc)
    return result
