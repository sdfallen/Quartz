"""Check the shipped application JavaScript without importing GUI/app state."""
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


def shipped_application_script():
    from ui.app_js import APPLICATION_JS, SCRIPT_DOCUMENT, SCRIPT_PARTS
    if not SCRIPT_PARTS or any(not isinstance(part, str) or not part.strip() for part in SCRIPT_PARTS):
        raise ValueError("Application JavaScript fragment missing or empty")
    script = application_script(SCRIPT_DOCUMENT)
    if script != APPLICATION_JS or APPLICATION_JS != "".join(SCRIPT_PARTS):
        raise ValueError("Application JavaScript composition differs from shipped script")
    return script


def main():
    try:
        script = shipped_application_script()
    except (ImportError, OSError, ValueError) as exc:
        print(str(exc))
        return 2
    result = subprocess.run(["node", "--check", "-"], input=script.encode("utf-8"), capture_output=True)
    print(result.stderr.decode("utf-8", errors="replace"))
    print("Embedded JS exit:", result.returncode)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
