"""Reusable path boundary checks for filesystem-capable tools and plugins."""

from pathlib import Path


class SandboxViolation(PermissionError):
    pass


class PathSandbox:
    def __init__(self, roots):
        self.roots = tuple(Path(root).resolve() for root in roots)
        if not self.roots:
            raise ValueError("At least one sandbox root is required")

    def resolve(self, path) -> Path:
        candidate = Path(path).expanduser().resolve()
        if not any(candidate == root or root in candidate.parents
                   for root in self.roots):
            raise SandboxViolation(f"Path is outside allowed roots: {candidate}")
        return candidate

    def allows(self, path) -> bool:
        try:
            self.resolve(path)
            return True
        except (OSError, SandboxViolation):
            return False
