# Quartz + Squad Architecture Discovery

## 20 October permission/checkpoint amendment

The current implementation supersedes historical safety/write descriptions below.
See `PERMISSION_CHECKPOINT_FIX_20261020.md`: read-only is the UI default;
project and explicit full access remain separate; permission denial never grants
consent. All service writers, including chat, pass through shared exclusion and
verified Git/file-archive checkpoints. Non-Git and untracked project files have
archive coverage; ignored/external data and whole-system changes do not.
Antigravity project-only writing is refused rather than silently escalated.
Write-enabled group chat uses one Codex writer followed by read-only Antigravity
review; read-only discussion stays parallel. Explicit single-agent full access
is available with confirmation, not advertised as project isolation.
ASTER registration remains blocked pending its separate integration contract.

## Baseline

- Quartz is a Python desktop application with a pywebview HTML/CSS/JavaScript UI.
- `main.py` owns a loopback-only JSON IPC server; `gui.py` is a thin UI client.
- `assistant.py` is the existing personal-assistant orchestrator. It keeps tool execution, confirmation, continuity, task tracking, memory, history and provider behavior intact.
- Existing model access is abstracted by `core/llm_provider.py`; NVIDIA and Groq remain available and are not silently removed or selected as fallbacks.
- Runtime user data lives in JSON and `.env` files beside the application. Those files, logs, screenshots and build output are excluded from Git.
- Packaging uses PyInstaller through `build.py`, with Inno Setup source under `installer/`.

Baseline checkpoint: `bdcab03` (`checkpoint: preserve working Quartz baseline`).

Baseline verification: 89 `unittest` tests passed on 2026-10-19. The suite emits socket `ResourceWarning` messages in some mocked IPC tests; those warnings predate this integration.

## Preserved components

- Existing chat, voice, mobile access, memory, history and continuity behavior.
- Existing direct desktop/application tools and their confirmation/safe-mode controls.
- Existing API provider manager and first-run API configuration.
- Existing compact window, Quartz Mode, launcher, updater and packaging flow.
- Existing user data and credentials.

## Integration boundary

```text
gui.py -> main.py IPC -> MultiAgentService
                           |-> ProjectRegistry
                           |-> SquadAdapter -> squad.exe -> project .squad/messages.db
                           |-> CodexRuntime -> codex.exe -> ChatGPT subscription session
                           `-> AntigravityRuntime -> agy.exe -> Google account session
```

Squad registration and a running model process are deliberately separate states. Squad remains the task/message coordination source; Quartz owns only processes it started and records their exact PID. The adapter never writes Squad SQLite directly.

## Verified local capabilities

- Squad 0.7.6 is installed at `C:\squad\squad.exe`.
- `C:\SquadPilot` contains an initialized `.squad/messages.db` workspace.
- Squad agent JSON, send/receive, task create/ack/complete/list and history commands work on Windows.
- `squad setup --list` incorrectly reports installed Windows npm launchers as missing; this is not used as CLI readiness evidence.
- Codex CLI 0.163.0 is installed and `codex login status` reports ChatGPT authentication.
- A real read-only `codex exec --json` run returned `QUARTZ_CODEX_RUNTIME_OK` using the subscription session.
- Google ended consumer Gemini CLI service for free and Google AI Pro/Ultra accounts on 2026-06-18. Quartz does not attempt to repair the retired OAuth route: <https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/>.
- The official Antigravity Windows installer resolves the current `windows_amd64` manifest and places `agy.exe` under `%LOCALAPPDATA%\agy\bin`: <https://www.antigravity.google/docs/cli/install/>.
- The installed binary is Antigravity CLI 1.4.2. Its 200,970,904-byte payload matched Google's manifest SHA-512 and has a valid `Google LLC` Authenticode signature.
- Cached Google-account authentication was discovered silently through the native credential store. `/model` returned `gemini-4-argon-medium`; `/usage` reported available account quotas. No browser sign-in or API key was required.
- `AntigravityRuntime` uses the documented `agy -p ... --output-format stream-json` contract and parses `init`, `step_update`, and terminal `result` events: <https://www.antigravity.google/docs/cli/headless/>.
- No Gemini API key is configured. Antigravity relies on the user's cached Google account sign-in.
- Squad 0.7.6 does not name Antigravity as a client type. Quartz therefore registers `quartz-antigravity` with the compatible `gemini` client label but performs all coordination through documented Squad `join`, `task`, `send`, `receive`, and `history` commands. This is shown in the UI as `Squad CLI köprüsü`.

## Safety decisions

- Only registered projects can be selected; initial scope is `C:\SquadPilot`.
- `C:\WarbandIsland` is not registered or touched in this implementation.
- UI-dispatched Codex tasks default to `read-only` with approval policy `never`.
- A `workspace-write` run requires an explicit confirmation and a per-project single-writer lock.
- Two-agent collaboration is read-only. Quartz never adds Antigravity's `--dangerously-skip-permissions` switch.
- Shell interpolation is not used. Arguments are passed as arrays; `.cmd` fallback uses `cmd.exe` with `subprocess.list2cmdline`.
- Cancellation targets only the exact `Popen` handle owned by Quartz.
- No OpenAI, Gemini or Vertex API key is created and no automatic paid-provider fallback is used.

## Planned/changed files

- `core/project_registry.py`: project isolation.
- `core/squad_adapter.py`: supported Squad CLI surface and parsers.
- `core/codex_runtime.py`: authenticated Codex process lifecycle and JSONL parsing.
- `core/antigravity_runtime.py`: official `agy` lifecycle and NDJSON parsing.
- `core/multi_agent_service.py`: real Squad task to real Codex run linkage.
- `main.py`, `gui.py`: IPC and existing-style control panel integration.
- `tests/`: argument safety, parsing, lifecycle and UI regression coverage.

## Codex + Antigravity collaboration flow

1. Quartz creates and ACKs a Codex analysis task.
2. The real Codex result is sent `quartz-codex -> quartz-antigravity` with `squad send`.
3. Quartz creates and ACKs an Antigravity review task and starts `agy`.
4. The real Antigravity review is sent `quartz-antigravity -> quartz-codex`.
5. Quartz creates a final Codex synthesis task and sends the result back to Antigravity.

The UI exposes Codex, Antigravity, and Codex + Antigravity modes. Runtime PIDs, terminal results, coordination errors, Squad tasks, and message history remain visible in the existing Ajan Merkezi.

## Live acceptance evidence

- Real collaboration completed three Squad tasks: Codex analysis `6dfb6428-9ea9-4cb6-9bd5-0a5e500dbc4e`, Antigravity review `6a3d6b43-c28f-4e16-90cb-650cd9097df9`, and Codex synthesis `271b9a80-dfeb-44ad-be17-89938501ad28`.
- Squad history contains all three bridge messages in both directions. Antigravity added a real technical correction about bounded item size, and the final Codex synthesis incorporated it.
- A real Quartz pywebview + IPC dispatch started Antigravity PID 11328 and completed Squad task `00ac03d0-4205-438c-9905-0a19ea74599f` with `QUARTZ_ANTIGRAVITY_IPC_OK`.
- The complete regression suite passed 113 tests after integration.
