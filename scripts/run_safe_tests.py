"""Run local regressions without sharing the desktop app's log or memory file.

Tests mock model providers; no live agent acceptance is implied by this runner.
"""
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _run_suite():
    import config
    with tempfile.TemporaryDirectory(prefix="quartz-test-logs-") as directory:
        config.LOG_FILE = str(Path(directory) / "tests.log")
        # assistant.py creates MemorySystem at import time. Redirect BEFORE
        # discovery imports assistant/main, including its deferred save timer.
        import memory_system
        memory_system.MEMORY_FILE = Path(directory) / "quartz_memory.json"
        memory_system._OLD_MEMORY_FILE = Path(directory) / "jarvis_memory.json"
        try:
            suite = (unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]) if len(sys.argv) > 1
                     else unittest.defaultTestLoader.discover(str(ROOT / "tests")))
            result = unittest.TextTestRunner(verbosity=1).run(suite)
        finally:
            assistant_module = sys.modules.get("assistant")
            if assistant_module is not None:
                memory = getattr(assistant_module, "memory", None)
                if isinstance(memory, memory_system.MemorySystem):
                    memory.shutdown()
            logging.shutdown()
    return 0 if result.wasSuccessful() else 1


def main():
    # A clean clone must not need a developer's real .env merely to construct
    # mocked SDK clients at import time. Never load local account keys here.
    # Provider calls remain mocked by tests; this sentinel is not a credential.
    values = {"NVIDIA_API_KEY": "quartz-offline-test-key",
              "GROQ_API_KEY": "quartz-offline-test-key",
              "GITHUB_TOKEN": "quartz-offline-test-key", "LLM_PROVIDER": "nvidia"}
    with patch.dict(os.environ, values), patch("dotenv.load_dotenv", return_value=False):
        return _run_suite()


if __name__ == "__main__":
    raise SystemExit(main())
