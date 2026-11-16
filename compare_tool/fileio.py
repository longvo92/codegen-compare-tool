"""Shared crash-safe file writing (standard library only)."""

import os
import tempfile
from pathlib import Path


def write_text_atomic(path, text, encoding='utf-8', newline='\n', parents=False):
    """Write ``text`` to ``path`` via a same-directory temp file and os.replace.

    The target is either the old or the new content, never a partial write.
    ``newline`` follows open(): '\\n' writes LF unchanged, None uses the platform
    default. A missing parent folder raises unless ``parents`` is true: a
    mistyped report path must fail, not create a stray tree. The temp file is
    always removed on failure and the OSError re-raised.
    """
    target = Path(path)
    if parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.' + target.name + '-', suffix='.tmp',
                                     dir=str(target.parent))
    try:
        with os.fdopen(fd, 'w', encoding=encoding, newline=newline) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target
