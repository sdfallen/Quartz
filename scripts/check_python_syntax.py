"""Compile only Python files included in the Git publication set."""

from pathlib import Path
import py_compile
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def published_python_files():
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-c", "-o", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    for relative in result.stdout.decode("utf-8").split("\0"):
        if relative.endswith(".py"):
            yield ROOT / relative


def main():
    files = sorted(published_python_files())
    for path in files:
        py_compile.compile(str(path), doraise=True)
    print(f"Published Python syntax: {len(files)} files OK")


if __name__ == "__main__":
    main()
