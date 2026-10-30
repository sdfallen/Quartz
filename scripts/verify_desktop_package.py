"""Check packaged code against this checkout without launching the desktop app."""
import hashlib
import json
from pathlib import Path
import sys
import types
import os
import subprocess
import marshal

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def code_signature(code):
    return (code.co_code, code.co_names, code.co_varnames, code.co_argcount,
            code.co_posonlyargcount, code.co_kwonlyargcount, code.co_flags,
            tuple(code_signature(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


def main():
    exe = Path(sys.argv[1])
    archive = CArchiveReader(str(exe))
    pyz = archive.open_embedded_archive("PYZ.pyz")
    checks = {}
    entry_source = ROOT / 'quartz_entry.py'
    checks['quartz_entry'] = code_signature(marshal.loads(archive.extract('quartz_entry'))) == code_signature(
        compile(entry_source.read_bytes(), str(entry_source), 'exec'))
    for module in ("gui", "main", "advanced_controller", "core.agent_chat", "core.conversation_store", "core.response_style", "core.local_ipc",
                   "core.cli_installer", "core.install_security", "core.windows_prerequisites", "core.self_diagnostics", "core.rea_adapter", "core.onboarding", "core.gemini_runtime", "core.gemini_auth", "core.low_spec_optimizer", "core.squad_adapter",
                   "core.desktop_agents", "core.desktop_control", "core.desktop_native", "core.desktop_broker",
                   "core.desktop_mcp", "core.desktop_launch", "core.desktop_task_ui", "core.natural_desktop", "core.warband_workspace", "core.project_registry", "core.multi_agent_service", "core.message_intent", "core.codex_runtime", "core.antigravity_runtime", "core.chat_coordination", "core.branding",
                   "core.async_snapshot", "core.task_outcome", "core.source_verification", "core.run_evidence_store", "core.writer_journal", "core.screen_overlay"):
        source = ROOT / (module.replace(".", "/") + ".py")
        if module not in pyz.toc:
            # desktop_mcp is a standalone helper, not imported into the GUI.
            checks[module] = "standalone helper" if module == "core.desktop_mcp" else False
            continue
        checks[module] = code_signature(pyz.extract(module)) == code_signature(compile(source.read_bytes(), str(source), "exec"))
    helper = exe.parent / "_internal/operator/QuartzDesktopMCP.exe"
    checks["helper_hash_matches"] = helper.is_file() and hashlib.sha256(helper.read_bytes()).digest() == hashlib.sha256((ROOT / "build/desktop-helper/QuartzDesktopMCP.exe").read_bytes()).digest()
    if helper.is_file():
        sys.path.insert(0,str(ROOT))
        from core.desktop_mcp import TOOLS
        env=os.environ.copy();env.pop("QUARTZ_DESKTOP_TOKEN",None);env.pop("QUARTZ_DESKTOP_URL",None)
        reply=subprocess.run([str(helper)],input=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/list"})+"\n",
            capture_output=True,text=True,encoding="utf-8",timeout=30,env=env)
        rows=[json.loads(line) for line in reply.stdout.splitlines() if line.strip()]
        checks["helper_schema_matches"]=reply.returncode==0 and len(rows)==1 and rows[0].get("result",{}).get("tools")==TOOLS
    css=exe.parent/"_internal/assets/workspace.css"
    checks["workspace_css_matches"]=css.is_file() and css.read_bytes()==(ROOT/"assets/workspace.css").read_bytes()
    brand=ROOT/'assets/branding/quartz-q.ico'
    if brand.is_file():
        from verify_branding import check_exe_icon
        checks['exe_q_icon_matches_supplied']=check_exe_icon(exe,brand)
        for name in ('quartz-q.ico','quartz-q.png','quartz-q-48.png'):
            packaged=exe.parent/'_internal/assets/branding'/name
            checks['brand_'+name]=packaged.is_file() and packaged.read_bytes()==(brand.parent/name).read_bytes()
    result = {"exe": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "checks": checks}
    print(json.dumps(result, indent=2))
    return 0 if all(value is True or value == "standalone helper" for value in checks.values()) else 1


if __name__ == "__main__": raise SystemExit(main())
