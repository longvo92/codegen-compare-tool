from pathlib import Path


def is_within(path: Path, root: Path) -> bool:
    """Test lexical containment, including equality, on Python 3.8."""
    return path == root or root in path.parents
