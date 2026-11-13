"""Incremental lane layout for a child-before-parent Git history."""

from __future__ import annotations

from typing import NamedTuple


class GraphRow(NamedTuple):
    incoming: tuple[int, ...]
    node: int
    outgoing: tuple[int, ...]
    shallow: bool


class Lanes:
    """Keep each pending parent in one lane until its row arrives."""

    def __init__(self):
        self.pending = []
        self.width = 1

    def _add(self, sha, preferred=None):
        if sha in self.pending:
            return self.pending.index(sha)
        if preferred is not None:
            lane = preferred
        elif None in self.pending:
            lane = self.pending.index(None)
        else:
            lane = len(self.pending)
            self.pending.append(None)
        self.pending[lane] = sha
        self.width = max(self.width, lane + 1)
        return lane

    def append(self, commit, parents=None):
        if parents is None:
            parents = commit.parents
        incoming = tuple(i for i, sha in enumerate(self.pending) if sha is not None)
        node = self._add(commit.sha)
        self.pending[node] = None
        outgoing = tuple(self._add(parent, node if index == 0 else None)
                         for index, parent in enumerate(parents))
        while self.pending and self.pending[-1] is None:
            self.pending.pop()
        return GraphRow(incoming, node, outgoing, commit.shallow)
