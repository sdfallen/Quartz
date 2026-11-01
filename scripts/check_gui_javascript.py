"""Parse the embedded GUI JavaScript without importing app state."""
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def application_script(source):
    scripts = re.findall(r"<script>(.*?)</script>", source, re.S)
    if len(scripts) != 1 or len(scripts[0].strip()) < 1000:
        raise ValueError("Application script block missing, duplicated or unexpectedly small")
    return scripts[0]


def main():
    source = (Path(__file__).resolve().parents[1] / "gui.py").read_text(encoding="utf-8")
    try:
        script = application_script(source)
    except ValueError as exc:
        print(str(exc))
        return 2
    result = subprocess.run(["node", "--check", "-"], input=script.encode("utf-8"), capture_output=True)
    print(result.stderr.decode("utf-8", errors="replace"))
    print("Embedded JS exit:", result.returncode)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
