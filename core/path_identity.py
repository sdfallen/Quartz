"""Stable filesystem identities across Windows path aliases.

Windows can expose the same directory through a long path and an 8.3 short
path (for example ``runneradmin`` and ``RUNNER~1``).  Security and ownership
checks must compare the resolved identity, not the spelling supplied by a
caller.
"""
import os
from pathlib import Path


def canonical_path(value, *, strict=False):
    return Path(value).expanduser().resolve(strict=strict)


def canonical_key(value, *, strict=False):
    return os.path.normcase(str(canonical_path(value, strict=strict)))


def canonical_relative(child, root):
    return canonical_path(child, strict=True).relative_to(
        canonical_path(root, strict=True)
    )
