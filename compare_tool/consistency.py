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

The reverse is **not** flagged. Code that changed while the ARXML and A2L did
not is the ordinary case: an internal logic or gain edit touches no interface
and no calibration variable, so there is nothing for them to follow.

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


def _families(rels, results):
    """``(present, changed)`` for one model's files: two ``{family: bool}``
    dicts over :data:`_FAMILIES`. ``present`` is True when the model has any
    file of that family in the compare at all; ``changed`` when at least one
    such file carries a reported change."""
    present = {f: False for f in _FAMILIES}
    changed = {f: False for f in _FAMILIES}
    for rel in rels:
        fam = ruleset_for(rel)
        if fam not in _FAMILIES:
            continue
        present[fam] = True
        if results[rel]['status'] in _CHANGED:
            changed[fam] = True
    return present, changed


def model_advisories(groups, results, shared_group=None):
    """``[(model, message)]`` for models whose ARXML or A2L really changed while
    the generated C did not.

    ``groups`` is ``{model: [rel, ...]}`` (the report's model grouping);
    ``shared_group`` names the catch-all bucket to skip, since it is not one
    model. A model is judged only when it has a C file in the compare -- with no
    generated code there is nothing that should have followed the change. A
    code-only change (C changed, the surfaces did not) is never flagged. Sorted
    by model name for a stable report and CLI.
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
    return out
