"""Pair an added file with a deleted one: the same file, moved or renamed.

`scanner` pairs files by relative path, which is right until the path is the
thing that changed. Rename a model, move `Foo.c` from `swc_a/` to `swc_b/`, or
restructure the output folders, and the tool reports one deleted file and one
added file -- two walls of text, with the reviewer left to work out for
themselves that nothing in them moved.

This module answers only "which added file *is* which deleted file". It takes
already-read data and returns pairs; `scanner` owns the file reading, and the
matching stays a pure function that can be tested without a filesystem.

**What a pair claims, and what it does not.** A pair is a reading aid: both
files stay in the results with their own `added` / `deleted` verdict, both stay
in the counts, and the exit code does not move. Saying "these two are the same
file" is a claim that can be wrong, so it is made only where it is not a guess
-- and being wrong costs the reviewer a confusing diff, never a missed change.

Three rules keep it honest, all of them from the same instinct as the noise
rules: a claim that cannot be proven is not made.

* **Same extension only.** A `.c` that became a `.h` is not a rename in a
  codegen tree, it is a different file that happens to share text.
* **Mutual best match.** The added file's best candidate must also have that
  added file as *its* best. A one-sided preference means something else fits
  better, and a pairing nobody agrees on is a guess.
* **A margin over the runner-up.** Generated files share banners, includes and
  a Rte call shape, so two unrelated SWCs score alarmingly well against each
  other. When the best and second-best are close, there is no answer here worth
  printing.

Similarity is measured on the **shadow** lines, not the raw ones: a regenerated
file that also moved has fresh UUIDs and timestamps on every other line, and
scoring the raw text would miss exactly the case this tool exists to handle.
Lines are compared as a MULTISET, so a file that was moved *and* reordered
still matches -- the question here is "is this the same file", not "did its
lines stay in order", which is what the line diff is for.

stdlib only: this ships in the zipapp.
"""

from collections import Counter

# git's own default is 50%. Codegen boilerplate scores higher than prose for
# unrelated files, so the bar is raised and paired with the margin below --
# the two together are what stop a confident wrong answer.
MIN_SIMILARITY = 0.60
MIN_MARGIN = 0.10

# Similarity is |added| x |deleted| comparisons. Exact-content matching (the
# common case: a pure move) is a dict lookup and always runs; the scored pass
# is skipped on a restructure big enough to make it slow. Nothing is hidden
# when it is skipped -- the files are all still reported, just not paired.
MAX_SCORED_PAIRS = 4000


class Candidate(object):
    """One side of a possible pair: what the matcher needs, already read.

    ``lines`` are the file's non-blank SHADOW lines (None for a binary file,
    which is matched on ``digest`` alone -- there is no meaningful partial
    similarity between two binaries).
    """

    __slots__ = ('rel', 'ext', 'digest', 'lines')

    def __init__(self, rel, ext, digest, lines=None):
        self.rel = rel
        self.ext = ext
        self.digest = digest
        self.lines = lines


def similarity(a_lines, b_lines):
    """How much of two files is the same text, as 0.0 - 1.0.

    ``2 * shared / (len(a) + len(b))`` over line multisets: 1.0 when the two
    hold the same lines, and symmetric, so neither side's length decides the
    answer on its own.
    """
    if not a_lines and not b_lines:
        return 1.0
    if not a_lines or not b_lines:
        return 0.0
    shared = sum((Counter(a_lines) & Counter(b_lines)).values())
    return 2.0 * shared / (len(a_lines) + len(b_lines))


def _exact_pairs(added, deleted):
    """Pairs whose content is byte-identical, by digest.

    Only claimed when exactly one file on each side carries that digest. Two
    added and two deleted files sharing content really did all move, but which
    went where is not knowable from the bytes, and naming a specific pair would
    invent an answer.
    """
    by_add, by_del = {}, {}
    for c in added:
        by_add.setdefault((c.ext, c.digest), []).append(c)
    for c in deleted:
        by_del.setdefault((c.ext, c.digest), []).append(c)
    out = {}
    for key, adds in by_add.items():
        dels = by_del.get(key)
        if dels and len(adds) == 1 and len(dels) == 1:
            out[adds[0].rel] = (dels[0].rel, 1.0)
    return out


def _scored_pairs(added, deleted):
    """Pairs of files that changed as well as moved, by shadow similarity."""
    if not added or not deleted:
        return {}
    if len(added) * len(deleted) > MAX_SCORED_PAIRS:
        return {}
    scores = {}
    per_add, per_del = {}, {}
    for a in added:
        for d in deleted:
            if a.ext != d.ext or a.lines is None or d.lines is None:
                continue
            s = similarity(a.lines, d.lines)
            if s >= MIN_SIMILARITY:
                scores[(a.rel, d.rel)] = s
                per_add.setdefault(a.rel, []).append(s)
                per_del.setdefault(d.rel, []).append(s)

    def top_two(vals):
        vals = sorted(vals, reverse=True)
        return vals[0], (vals[1] if len(vals) > 1 else 0.0)

    best = {rel: top_two(v) for rel, v in per_add.items()}
    best_d = {rel: top_two(v) for rel, v in per_del.items()}

    out = {}
    for (a_rel, d_rel), s in scores.items():
        a_best, a_second = best[a_rel]
        d_best, d_second = best_d[d_rel]
        # mutual best, and clear of the runner-up on BOTH sides
        if (s == a_best and s == d_best
                and s - a_second >= MIN_MARGIN and s - d_second >= MIN_MARGIN):
            out[a_rel] = (d_rel, s)
    return out


def find_moves(added, deleted):
    """Match added files to deleted ones.

    ``added`` / ``deleted`` are :class:`Candidate` lists. Returns
    ``{added_rel: (deleted_rel, similarity)}`` holding only pairs the rules
    above agree on; an unmatched file simply does not appear.
    """
    pairs = _exact_pairs(added, deleted)
    taken_del = {d for d, _s in pairs.values()}
    rest_add = [c for c in added if c.rel not in pairs]
    rest_del = [c for c in deleted if c.rel not in taken_del]
    pairs.update(_scored_pairs(rest_add, rest_del))
    return pairs
