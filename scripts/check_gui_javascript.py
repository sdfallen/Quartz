"""Parse the embedded GUI JavaScript without importing app state."""
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.document import NOTION_TOOLS_SCRIPT

source = (Path(__file__).resolve().parents[1] / "gui.py").read_text(encoding="utf-8")
scripts = re.findall(r"<script>(.*?)</script>", source, re.S)
scripts.append(NOTION_TOOLS_SCRIPT)
result = subprocess.run(["node", "--check", "-"], input="\n".join(scripts).encode("utf-8"), capture_output=True)
print(result.stderr.decode("utf-8", errors="replace"))
print("Embedded JS exit:", result.returncode)
raise SystemExit(result.returncode)
