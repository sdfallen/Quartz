# Quartz Tool Workbench Lab & Testbed

This laboratory workspace contains test fixtures, manifests, and verification utilities for the `core/tool_workbench` system.

## Components

- `fixture_factory.py`: Generator for security test archives:
  - Valid tool archives for verification
  - Zip-Slip path traversal attack archives (`../../escaped_malicious.exe`)
  - Absolute path attack archives (`C:/Windows/System32/evil.dll`)
  - Symlink attack archives
  - Corrupted and truncated archives
- Verified tool manifests:
  - `ripgrep` (BurntSushi/ripgrep 14.1.1)
  - `pe_inspector` (PE structure and header inspector)
  - `rea_static` (REA static artifact adapter)

## Testing Commands

Run the full workbench test suite:
```powershell
python -B -m unittest discover -s tests -p "test_tool_workbench_*.py"
```

Run real resource measurements:
```powershell
python -B scripts/tool_workbench_benchmark.py
```

Run real tool acquisition and execution demo:
```powershell
python -B scripts/tool_workbench_acquire_demo.py
```
