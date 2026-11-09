"""Pre-task environment health checks for Quartz agent runs.

Contract: docs/INTEGRATION_REQUEST_ENVIRONMENT_HEALTH_20261109.md
Acceptance gate 1 of docs/THREE_AGENT_WEEK_PLAN_20261109.md.

Rules:
- Read-only: never modifies the environment, PATH, user settings, or project files.
- Bounded budget: each subprocess has <= 2.0s timeout; total budget <= 3.0s; no network calls.
- Bounded texts: summary_tr <= 120 chars, fix_tr <= 160 chars, detail <= 500 chars.
- No secrets, tokens, account names, or full environment dumps in output fields.
- 60s cache keyed by normalized (project_path, mode, write, desktop, squad/agents snapshot);
  force=True bypasses the cache.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time


CACHE_TTL_SECONDS = 60.0
SUBPROCESS_TIMEOUT_SECONDS = 1.5
MAX_SUMMARY_LEN = 120
MAX_FIX_LEN = 160
MAX_DETAIL_LEN = 500

_CACHE_LOCK = threading.RLock()
_CACHE: dict[tuple, tuple[float, dict]] = {}

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)


def _sanitize_text(text: str | None, max_len: int) -> str:
    raw = " ".join(str(text or "").strip().split())
    if not raw:
        return ""
    for pattern in _SECRET_PATTERNS:
        raw = pattern.sub("[REDACTED]", raw)
    if len(raw) > max_len:
        return raw[: max_len - 1].rstrip() + "…"
    return raw


def _make_check(
    check_id: str,
    status: str,
    summary_tr: str,
    fix_tr: str = "",
    detail: str = "",
    evidence: dict | None = None,
) -> dict:
    if status not in {"ok", "warn", "blocked", "unknown"}:
        status = "unknown"
    return {
        "id": str(check_id),
        "status": status,
        "summary_tr": _sanitize_text(summary_tr, MAX_SUMMARY_LEN),
        "fix_tr": _sanitize_text(fix_tr, MAX_FIX_LEN),
        "detail": _sanitize_text(detail, MAX_DETAIL_LEN),
        "evidence": dict(evidence or {}),
    }


def _worst_status(checks: list[dict]) -> str:
    statuses = {c.get("status") for c in checks}
    if "blocked" in statuses:
        return "blocked"
    if "warn" in statuses or "unknown" in statuses:
        return "warn"
    return "ok"


def _normalize_mode(mode: str | None) -> str:
    raw = str(mode or "collaboration").strip().lower()
    if raw in {"both", "collaboration", "codex-antigravity"}:
        return "collaboration"
    if raw in {"agy", "antigravity", "gemini"}:
        return "antigravity"
    if raw == "codex":
        return "codex"
    return raw or "collaboration"


def _selected_agents(mode: str) -> set[str]:
    if mode == "collaboration":
        return {"codex", "antigravity"}
    if mode == "codex":
        return {"codex"}
    if mode == "antigravity":
        return {"antigravity"}
    return {"codex", "antigravity"}


def _is_windows_store_alias(path_str: str | None) -> bool:
    if not path_str:
        return False
    norm = str(path_str).replace("/", "\\").lower()
    return "\\microsoft\\windowsapps\\" in norm or "pythonsoftwarefoundation.python." in norm


def _run_subprocess(cmd: list[str], *, cwd: str | None = None, env: dict | None = None, timeout: float = SUBPROCESS_TIMEOUT_SECONDS, runner=None) -> dict:
    run_fn = runner or subprocess.run
    t0 = time.monotonic()
    try:
        completed = run_fn(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(2.0, max(0.1, float(timeout))),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
        return {
            "ok": completed.returncode == 0,
            "exit_code": int(completed.returncode),
            "stdout": str(completed.stdout or "").strip(),
            "stderr": str(completed.stderr or "").strip(),
            "elapsed_ms": elapsed_ms,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "Alt süreç zaman aşımına uğradı.",
            "elapsed_ms": elapsed_ms,
            "timed_out": True,
        }
    except OSError as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "elapsed_ms": elapsed_ms,
            "timed_out": False,
        }


def _check_project_folder(project_path: str | Path | None) -> tuple[dict, Path | None]:
    t0 = time.monotonic()
    raw = str(project_path or "").strip()
    if not raw:
        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
        return (
            _make_check(
                "project_folder",
                "blocked",
                "Proje klasörü seçilmedi.",
                "Sol çekmeceden geçerli bir proje klasörü seçin veya ekleyin.",
                "project_path boş.",
                {"path": "", "exists": False, "readable": False, "elapsed_ms": elapsed_ms},
            ),
            None,
        )
    try:
        resolved = Path(raw).resolve()
        exists = resolved.exists()
        is_dir = resolved.is_dir()
        readable = False
        detail = str(resolved)
        if exists and is_dir:
            with os.scandir(resolved) as it:
                next(it, None)
            readable = True
        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
        if not exists or not is_dir:
            return (
                _make_check(
                    "project_folder",
                    "blocked",
                    "Proje klasörü bulunamadı.",
                    "Klasör yolunu kontrol edin veya projeyi yeniden seçin.",
                    f"Klasör mevcut değil: {resolved}",
                    {"path": str(resolved), "exists": exists, "readable": False, "elapsed_ms": elapsed_ms},
                ),
                None,
            )
        return (
            _make_check(
                "project_folder",
                "ok",
                "Proje klasörü erişilebilir.",
                "",
                str(resolved),
                {"path": str(resolved), "exists": True, "readable": readable, "elapsed_ms": elapsed_ms},
            ),
            resolved,
        )
    except OSError as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
        return (
            _make_check(
                "project_folder",
                "blocked",
                "Proje klasörü okunamıyor.",
                "Klasör izinlerini kontrol edin veya erişilebilir bir proje seçin.",
                f"{raw}: {exc}",
                {"path": raw, "exists": False, "readable": False, "elapsed_ms": elapsed_ms},
            ),
            None,
        )


def _check_python(env: dict | None = None, *, runner=None, which_fn=None) -> dict:
    path_env = (env or os.environ).get("PATH")
    resolve_which = which_fn or (lambda name: shutil.which(name, path=path_env))
    which_python = resolve_which("python")
    python_cmd = which_python if (which_python and runner is None) else "python"
    res = _run_subprocess(
        [python_cmd, "-c", "import sys; print(sys.executable); print(sys.version.split()[0])"],
        env=env,
        runner=runner,
    )
    lines = [line.strip() for line in res["stdout"].splitlines() if line.strip()]
    exe_out = lines[0] if lines else (which_python or "")
    ver_out = lines[1] if len(lines) > 1 else ""
    store_alias = _is_windows_store_alias(which_python) or _is_windows_store_alias(exe_out)
    evidence = {
        "executable": exe_out or which_python or "",
        "which": which_python or "",
        "version": ver_out,
        "store_alias": store_alias,
        "exit_code": res["exit_code"],
        "elapsed_ms": res["elapsed_ms"],
    }
    if not res["ok"] or not exe_out:
        detail = res["stderr"] or res["stdout"] or "PATH üzerinde çalışan bir python komutu bulunamadı."
        if store_alias:
            return _make_check(
                "python",
                "warn",
                "Python Microsoft Store takma adı çalışmadı; ajanlar test koşamayabilir.",
                "python.org Python kurun veya PATH'te Store takma adından önce gelen bir Python kullanın.",
                f"{which_python or 'python'} -> {detail}",
                evidence,
            )
        return _make_check(
            "python",
            "warn",
            "PATH üzerinde çalışan bir Python bulunamadı.",
            "python.org Python kurup PATH ortam değişkenine ekleyin.",
            detail,
            evidence,
        )
    if store_alias:
        return _make_check(
            "python",
            "warn",
            "Python Microsoft Store takma adı; ajanlarda aralıklı başarısız olabilir.",
            "python.org Python kurun veya PATH'te Store takma adından önce gelen bir Python kullanın.",
            f"{which_python or exe_out} -> {ver_out or 'AppExecLink'}",
            evidence,
        )
    return _make_check(
        "python",
        "ok",
        f"Python hazır ({ver_out or 'ok'}).",
        "",
        f"{exe_out} ({ver_out})" if ver_out else exe_out,
        evidence,
    )


def _check_git(project_dir: Path | None, *, write: bool = False, env: dict | None = None, runner=None, which_fn=None) -> dict:
    path_env = (env or os.environ).get("PATH")
    resolve_which = which_fn or (lambda name: shutil.which(name, path=path_env))
    git_exe = resolve_which("git")
    ver_res = _run_subprocess(["git", "--version"], env=env, runner=runner)
    if not ver_res["ok"]:
        status = "blocked" if write else "warn"
        summary = (
            "Git bulunamadı; yazıcı görev güvenlik noktası (checkpoint) olmadan başlayamaz."
            if write
            else "Git bulunamadı; sürüm kontrolü kullanılamaz."
        )
        return _make_check(
            "git",
            status,
            summary,
            "Git kurun ve PATH ortam değişkenine eklendiğinden emin olun.",
            ver_res["stderr"] or "git --version başarısız.",
            {
                "executable": git_exe or "",
                "installed": False,
                "is_repo": False,
                "exit_code": ver_res["exit_code"],
                "elapsed_ms": ver_res["elapsed_ms"],
            },
        )
    git_version = ver_res["stdout"].splitlines()[0] if ver_res["stdout"] else "git"
    if project_dir is None:
        return _make_check(
            "git",
            "warn",
            "Proje klasörü erişilemediği için Git deposu kontrol edilemedi.",
            "Önce geçerli bir proje klasörü seçin.",
            git_version,
            {
                "executable": git_exe or "git",
                "installed": True,
                "is_repo": False,
                "exit_code": ver_res["exit_code"],
                "elapsed_ms": ver_res["elapsed_ms"],
            },
        )
    repo_res = _run_subprocess(
        ["git", "-C", str(project_dir), "rev-parse", "--is-inside-work-tree"],
        env=env,
        runner=runner,
    )
    total_ms = round(ver_res["elapsed_ms"] + repo_res["elapsed_ms"], 1)
    is_repo = repo_res["ok"] and repo_res["stdout"].strip().lower() == "true"
    evidence = {
        "executable": git_exe or "git",
        "version": git_version,
        "installed": True,
        "is_repo": is_repo,
        "exit_code": repo_res["exit_code"],
        "elapsed_ms": total_ms,
    }
    if not is_repo:
        return _make_check(
            "git",
            "warn",
            "Proje klasörü bir Git deposu değil; Git checkpoint alınamayacak.",
            "Git checkpoint için projede 'git init' çalıştırabilir veya arşiv yedeğiyle devam edebilirsiniz.",
            repo_res["stderr"] or f"{project_dir} içinde .git bulunamadı ({git_version}).",
            evidence,
        )
    return _make_check(
        "git",
        "ok",
        "Git ve proje deposu hazır.",
        "",
        f"{git_version} · {project_dir}",
        evidence,
    )


def _probe_squad_fallback(project_dir: Path | None) -> dict:
    if project_dir is None:
        return {"installed": False, "initialized": False, "connected": False, "error": "Proje klasörü yok."}
    try:
        from core.squad_adapter import SquadAdapter
        adapter = SquadAdapter(project_dir, timeout=2)
        st = adapter.status()
        connected = bool(st.get("installed")) and bool(st.get("initialized")) and not st.get("error")
        return {**st, "connected": connected}
    except Exception as exc:
        return {"installed": False, "initialized": False, "connected": False, "error": str(exc)}


def _check_squad(
    project_dir: Path | None,
    *,
    mode: str,
    desktop: bool,
    squad_info: dict | None,
) -> dict:
    t0 = time.monotonic()
    info = dict(squad_info) if isinstance(squad_info, dict) else _probe_squad_fallback(project_dir)
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
    squad_mode = str(info.get("mode") or "project")
    installed = bool(info.get("installed", True if info.get("connected") or info.get("ready") else False))
    initialized = bool(info.get("initialized", True if info.get("connected") else False))
    err = str(info.get("error") or "").strip()
    if squad_mode == "task-isolated":
        connected = bool(info.get("ready") or info.get("installed")) and not err
    elif "connected" in info:
        connected = bool(info.get("connected")) and not err
    else:
        connected = installed and initialized and not err

    evidence = {
        "connected": connected,
        "installed": installed,
        "initialized": initialized,
        "mode": squad_mode,
        "elapsed_ms": elapsed_ms,
    }
    if connected:
        return _make_check(
            "squad",
            "ok",
            "Squad koordinasyon veritabanı bağlı.",
            "",
            str(info.get("database") or info.get("workspace") or "Squad hazır."),
            evidence,
        )
    if bool(info.get("checking")) and not err:
        return _make_check(
            "squad",
            "unknown",
            "Squad bağlantısı kontrol ediliyor.",
            "Kontrol tamamlanana kadar bekleyin veya 'Yeniden kontrol et' düğmesine basın.",
            str(info.get("message") or "Squad durumu henüz doğrulanmadı."),
            evidence,
        )
    requires_squad = (mode == "collaboration") or bool(desktop)
    status = "blocked" if requires_squad else "warn"
    summary = (
        "Squad bağlı değil; Birlikte modu ve masaüstü görevleri Squad gerektirir."
        if requires_squad
        else "Squad bu projede henüz hazır değil (tek ajan sohbeti çalışabilir)."
    )
    fix = "Projeyi yeniden seçin veya proje klasöründe 'squad init' çalıştırıp 'Yeniden kontrol et'e basın."
    detail = err or str(info.get("message") or "Squad çalışma alanı (.squad/messages.db) hazır değil.")
    return _make_check("squad", status, summary, fix, detail, evidence)


def _extract_agent_diag(provider: str, agents: dict | None) -> dict | None:
    if not isinstance(agents, dict):
        return None
    if isinstance(agents.get(provider), dict):
        return dict(agents[provider])
    nested = agents.get("agents")
    if isinstance(nested, dict) and isinstance(nested.get(provider), dict):
        return dict(nested[provider])
    return None


def _probe_agent_fallback(provider: str) -> dict:
    try:
        if provider == "codex":
            from core.codex_runtime import CodexRuntime
            return CodexRuntime().probe()
        from core.antigravity_runtime import AntigravityRuntime
        return AntigravityRuntime().probe()
    except Exception as exc:
        return {"installed": False, "authenticated": False, "ready": False, "error": str(exc)}


def _check_cli_agent(provider: str, *, selected: bool, agents: dict | None) -> dict:
    check_id = f"{provider}_cli"
    label = "Codex CLI" if provider == "codex" else "Antigravity CLI"
    t0 = time.monotonic()
    info = _extract_agent_diag(provider, agents)
    if info is None:
        info = _probe_agent_fallback(provider)
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)

    if not info and not selected:
        return _make_check(
            check_id,
            "ok",
            f"{label} bu modda seçili değil.",
            "",
            "",
            {"selected": False, "ready": None, "elapsed_ms": elapsed_ms},
        )

    installed = bool(info.get("installed"))
    authenticated = bool(info.get("authenticated", info.get("ready")))
    ready = bool(info.get("ready", installed and authenticated))
    err = str(info.get("error") or "").strip()
    version = str(info.get("version") or "").strip()
    evidence = {
        "selected": selected,
        "installed": installed,
        "authenticated": authenticated,
        "ready": ready,
        "version": version,
        "elapsed_ms": elapsed_ms,
    }
    if ready:
        return _make_check(
            check_id,
            "ok",
            f"{label} hazır.",
            "",
            version or f"{label} kurulu ve giriş yapılmış.",
            evidence,
        )
    if bool(info.get("checking")) and not err:
        return _make_check(
            check_id,
            "unknown",
            f"{label} durumu kontrol ediliyor.",
            "Birkaç saniye bekleyip 'Yeniden kontrol et' düğmesine basın.",
            version,
            evidence,
        )

    status = "blocked" if selected else "warn"
    if not installed:
        summary = f"{label} kurulu değil." if selected else f"{label} kurulu değil (bu görevde seçili değil)."
        fix = (
            f"Quartz kurulum ekranından veya terminalden {label} kurulumunu tamamlayın."
        )
    elif not authenticated:
        summary = (
            f"{label} oturumu açık değil."
            if selected
            else f"{label} oturumu açık değil (bu görevde seçili değil)."
        )
        fix = (
            "Codex CLI için 'codex login' ile giriş yapın."
            if provider == "codex"
            else "Antigravity CLI için Google hesabınızla giriş yapın ('agy' oturumu)."
        )
    else:
        summary = f"{label} hazır değil." if selected else f"{label} hazır değil (bu görevde seçili değil)."
        fix = f"{label} bağlantısını kontrol edip 'Yeniden kontrol et' düğmesine basın."
    detail = err or f"installed={installed}, authenticated={authenticated}, ready={ready}"
    return _make_check(check_id, status, summary, fix, detail, evidence)


def _cache_signature(
    project_path: str,
    mode: str,
    write: bool,
    desktop: bool,
    agents: dict | None,
    squad: dict | None,
    path_value: str,
) -> tuple:
    try:
        agents_sig = json.dumps(agents or {}, sort_keys=True, default=str)
    except Exception:
        agents_sig = str(agents)
    try:
        squad_sig = json.dumps(squad or {}, sort_keys=True, default=str)
    except Exception:
        squad_sig = str(squad)
    return (
        os.path.normcase(str(project_path or "")),
        mode,
        bool(write),
        bool(desktop),
        agents_sig,
        squad_sig,
        path_value,
    )


def clear_cache() -> None:
    """Clear the 60-second health check cache (used by tests or explicit resets)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def check(
    project_path: str | Path | None,
    *,
    mode: str = "collaboration",
    agents: dict | None = None,
    squad: dict | None = None,
    write: bool = False,
    desktop: bool = False,
    force: bool = False,
    env: dict | None = None,
    runner=None,
    which_fn=None,
) -> dict:
    """Evaluate pre-task environment health according to INTEGRATION_REQUEST_ENVIRONMENT_HEALTH_20261109.md."""
    norm_mode = _normalize_mode(mode)
    selected = _selected_agents(norm_mode)

    # Allow callers to pass chat_status or raw_status directly in `agents` and/or `squad`.
    resolved_squad = squad
    if resolved_squad is None and isinstance(agents, dict) and isinstance(agents.get("squad"), dict):
        resolved_squad = agents["squad"]

    effective_env = env
    if effective_env is None:
        try:
            from core.cli_installer import cli_environment
            effective_env = cli_environment()
        except Exception:
            effective_env = os.environ.copy()

    raw_project = str(project_path or "").strip()
    cache_key = _cache_signature(
        raw_project,
        norm_mode,
        write,
        desktop,
        agents,
        resolved_squad,
        str((effective_env or os.environ).get("PATH") or ""),
    )
    now_mono = time.monotonic()
    if not force:
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached is not None and (now_mono - cached[0]) < CACHE_TTL_SECONDS:
                return deepcopy(cached[1])

    folder_check, resolved_dir = _check_project_folder(project_path)
    python_check = _check_python(effective_env, runner=runner, which_fn=which_fn)
    git_check = _check_git(resolved_dir, write=bool(write), env=effective_env, runner=runner, which_fn=which_fn)
    squad_check = _check_squad(
        resolved_dir,
        mode=norm_mode,
        desktop=bool(desktop),
        squad_info=resolved_squad,
    )
    codex_check = _check_cli_agent("codex", selected=("codex" in selected), agents=agents)
    agy_check = _check_cli_agent("antigravity", selected=("antigravity" in selected), agents=agents)

    checks = [
        python_check,
        git_check,
        folder_check,
        squad_check,
        codex_check,
        agy_check,
    ]
    result = {
        "checked_at": time.time(),
        "project_path": str(resolved_dir) if resolved_dir is not None else raw_project,
        "mode": norm_mode,
        "status": _worst_status(checks),
        "checks": checks,
    }
    with _CACHE_LOCK:
        _CACHE[cache_key] = (time.monotonic(), deepcopy(result))
    return result
