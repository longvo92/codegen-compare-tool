"""Cross-artifact consistency advisories.

A model's ARXML (its contract) and its generated C (its behaviour) are produced
by the same regenerate and are expected to move together. When one is
regenerated and the other is not, the folder holds a *mix* that the per-file
diff cannot point at: each file is individually fine — Modified, or Identical —
and the inconsistency lives strictly *between* them. That is the one thing a
file-by-file view structurally cannot show, and the everyday cause is a partial
or stale regenerate.

This is an **advisory, never a verdict**. Absence of a partner change can be
perfectly legitimate — a hand-written file kept beside generated ones, an ARXML
edited on its own, a symbol defined in another folder — so it must not fold a
file, move a count, or change the exit code. It says "worth a look", not
"wrong". The claim the rest of the tool makes ("you can ignore what I hid") is
never put at risk by a guess, because this makes no claim about noise at all: it
only reports which artifact families of a model carry a change the tool already
stands behind.

Only the C <-> ARXML pair is checked. A2L (calibration) legitimately changes on
its own — a recal touches no code — so pairing it here would cry wolf.

Stdlib only, no Qt: the report and the CLI both import it.
"""

from .diff_engine import ruleset_for

# a family carries a change when at least one of its files got one of these
# verdicts -- the ones the tool reports as "something happened here"
_CHANGED = frozenset(('real-change', 'added', 'deleted'))
_FAMILIES = ('c', 'arxml')


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
    """``[(model, message)]`` for models whose generated C and ARXML did not
    change together.

    ``groups`` is ``{model: [rel, ...]}`` (the report's model grouping);
    ``shared_group`` names the catch-all bucket to skip, since it is not one
    model. Only models that have BOTH a C and an ARXML file in the compare are
    judged — with only one family present there is no partner to be out of step
    with. Sorted by model name for a stable report and CLI.
    """
    out = []
    for model in sorted(groups):
        if shared_group is not None and model == shared_group:
            continue
        present, changed = _families(groups[model], results)
        if not (present['c'] and present['arxml']):
            continue
        if changed['c'] and not changed['arxml']:
            out.append((model, 'generated C changed but its ARXML did not — '
                               'check the model was fully regenerated'))
        elif changed['arxml'] and not changed['c']:
            out.append((model, 'ARXML changed but its generated C did not — '
                               'the code may not have been regenerated'))
    return out
