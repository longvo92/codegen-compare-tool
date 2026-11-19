"""Embedded Coder file naming: which model a generated file belongs to."""


def stem(rel):
    """File name without its last extension, from a posix or native path."""
    base = str(rel).replace('\\', '/').rsplit('/', 1)[-1]
    dot = base.rfind('.')
    return base[:dot] if dot > 0 else base


def model_of(name, ordered_models):
    """Owning model of a file stem: X.ext, X_*.ext or Rte_X.h belong to X.
    ``ordered_models`` is longest-first so SubModel_ab wins over SubModel."""
    for m in ordered_models:
        if name == m or name.startswith(m + '_') or name == 'Rte_' + m:
            return m
    return None
