"""Cross-artifact consistency advisories.

A model's ARXML is its contract and its A2L is its calibration surface; both are
realised by the generated C. So the dependency runs one way: if the **interface
or the calibration really changed, the code must have changed too** -- a new
port needs a new RTE access, a new characteristic needs a new symbol. When an
ARXML or A2L change lands with no corresponding change in the generated C, the
folder holds a mix that the per-file diff cannot point at: each file is
individually fine, and the inconsistency lives strictly *between* them. The
everyday cause is a stale or partial regenerate -- the model was re-exported but
the code was not.

"Really changed" is measured at the **access-point level, not the file level**.
The trigger is a parsed port-interface / SWC port·runnable·event added or
removed (ARXML), or a calibration object added or removed (A2L) -- never the
mere fact that the file's bytes differ. Base types, compu-methods and other
shared library packages get rewritten on every export without touching a single
access point; keying the advisory on the file's verdict flagged that churn as a
desync, which is exactly the false alarm this level of granularity removes.

The reverse is **not** flagged. Code that changed while the ARXML and A2L did
not is the ordinary case: an internal logic or gain edit touches no interface
and no calibration variable, so there is nothing for them to follow.

A second, cross-*model* advisory rides along here. When one model's generated C
gains an RTE access point (``+ Rte_Write_...``) while a *peer* model's C stayed
byte-identical, the batch was a single-model quick regen, not a full one: a full
regenerate rewrites at least a timestamp banner in every model, so an identical
peer is proof it was left untouched. A new RTE access widens the model's
interface, and the RTE layer plus the peer SWCs have to be regenerated before
the code will integrate -- so this ``+RTE`` cannot be shipped on its own.

This is an **advisory, never a verdict**. It never folds a file, moves a count
or changes the exit code. It only reports which artifact families of a model
carry a change the tool already stands behind.

Stdlib only, no Qt: the report and the CLI both import it.
"""

from .diff_engine import ruleset_for

# a family carries a change when at least one of its files got one of these
# verdicts -- the ones the tool reports as "something happened here"
_CHANGED = frozenset(('real-change', 'added', 'deleted'))
_FAMILIES = ('c', 'arxml', 'a2l')

# the interface / calibration surfaces, and how each is spelled in the advisory
_SURFACES = (('arxml', 'ARXML'), ('a2l', 'A2L'))


def _iface_changed(r):
    """True when an ARXML file's interface surface really moved -- a
    port-interface or an SWC port/runnable/event was added, removed or
    retargeted. This is the ONLY ARXML change the code has to follow; library
    packages (base types, compu-methods, units) churn on every export without
    touching an access point, so keying on the file's verdict would flag them.

    ``ifaces`` is stored whenever the file PARSED, even with an empty diff, so
    its presence is the marker for "the semantic pass actually ran". An empty
    diff is therefore a proof of noise and stays quiet; an ABSENT key on a
    changed file means the pass could not run at all -- binary content, or XML
    that would not parse -- and proves nothing, so it counts as changed. That is
    the fail-safe direction: unprovable is never noise. ``swc`` is stored only
    when non-empty, so its presence is already a real move."""
    d = r.get('ifaces')
    if d is None:
        return r['status'] in _CHANGED
    return bool(d['added'] or d['removed'] or r.get('swc'))


def _a2l_changed(r):
    """True when an A2L file added or removed a calibration object. A changed
    value or record layout is not a new symbol, so it needs no code; ``a2l`` is
    stored only when an object was added or removed, so an absent key on a text
    file means the scan looked and found nothing to follow.

    A BINARY a2l is the one file the scan never looked at, and an unexamined
    change proves nothing -- same fail-safe direction as :func:`_iface_changed`.
    (The scanner only marks ``binary`` on the two-sided compare path; a binary
    a2l that was added or deleted outright is not distinguishable here.)"""
    return bool(r.get('a2l')) or (r['status'] in _CHANGED and r.get('binary', False))


def _families(rels, results):
    """``(present, changed)`` for one model's files: two ``{family: bool}``
    dicts over :data:`_FAMILIES`. ``present`` is True when the model has any
    file of that family in the compare at all. ``changed`` is where the
    access-point granularity lives: for ``c`` it is any reported code change
    (that is the follow we are checking for); for ``arxml`` / ``a2l`` it is a
    real access-point / object move, read from the parsed semantic diff -- not
    the file's verdict, so library churn does not raise the advisory."""
    present = {f: False for f in _FAMILIES}
    changed = {f: False for f in _FAMILIES}
    for rel in rels:
        fam = ruleset_for(rel)
        if fam not in _FAMILIES:
            continue
        present[fam] = True
        r = results[rel]
        if fam == 'c':
            if r['status'] in _CHANGED:
                changed['c'] = True
        elif fam == 'arxml':
            if _iface_changed(r):
                changed['arxml'] = True
        elif fam == 'a2l':
            if _a2l_changed(r):
                changed['a2l'] = True
    return present, changed


def model_advisories(groups, results, shared_group=None):
    """``[(model, message)]`` for models whose ARXML or A2L really changed while
    the generated C did not.

    ``groups`` is ``{model: [rel, ...]}`` (the report's model grouping);
    ``shared_group`` names the catch-all bucket to skip, since it is not one
    model. A model is judged only when it has a C file in the compare -- with no
    generated code there is nothing that should have followed the change. A
    code-only change (C changed, the surfaces did not) is never flagged.

    Both kinds of advisory come back in ONE list sorted by model name: the two
    are gathered by separate passes, and concatenating them would order the
    report and the CLI by which rule fired rather than by which model the
    reviewer is looking for.
    """
    out = []
    for model in sorted(groups):
        if shared_group is not None and model == shared_group:
            continue
        present, changed = _families(groups[model], results)
        if not present['c'] or changed['c']:
            # no code to have followed, or the code changed too -- both fine
            continue
        surfaces = [label for fam, label in _SURFACES
                    if present[fam] and changed[fam]]
        if surfaces:
            out.append((model, '{} changed but the generated C did not'
                               .format(' and '.join(surfaces))))
    out.extend(_rte_regen_advisories(groups, results, shared_group))
    # a model can never earn both (the +RTE rule needs its C to have changed,
    # the surface rule needs it not to have), so sorting by name alone is stable
    out.sort(key=lambda row: row[0])
    return out


def _c_status(rels, results):
    """Statuses of a model's C-family files (``.c`` and ``.h``)."""
    return [results[rel]['status'] for rel in rels if ruleset_for(rel) == 'c']


def _rte_regen_advisories(groups, results, shared_group):
    """``[(model, message)]`` for models that gained an RTE access point while a
    peer model's C stayed byte-identical -- the tell of a single-model quick
    regen. A ``+RTE`` cannot be integrated until the RTE layer and the peers are
    regenerated too, so it is flagged even when the model's own files are all
    self-consistent. Advisory only; see the module docstring.
    """
    # a model whose C is entirely identical was not regenerated in this batch:
    # a real regenerate rewrites at least a timestamp banner (ignorable-only),
    # so identical -- not merely noisy -- is the exact proof it was skipped.
    identical = set()
    rte_added = set()
    for model in groups:
        if shared_group is not None and model == shared_group:
            continue
        cs = _c_status(groups[model], results)
        if cs and all(s == 'identical' for s in cs):
            identical.add(model)
        for rel in groups[model]:
            d = results[rel].get('rte')
            if d and d.get('added'):
                rte_added.add(model)
                break
    if not identical:
        return []  # no skipped peer, so nothing here is evidence of a quick regen
    # a model carrying a +RTE always has a changed .c (that is where the access
    # point was found), so it can never be one of the identical peers itself
    return [(model, 'gained an RTE access while a peer model stayed identical '
                    '-- regenerate the architecture before integrating')
            for model in sorted(rte_added)]
