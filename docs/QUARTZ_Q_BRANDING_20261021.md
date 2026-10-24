# Quartz approved Q integration — 21 October 2026

This continuation replaces the earlier missing-artwork blocker. It does not
retroactively change earlier GUI or desktop-coordination acceptance results.

## Supplied assets

- Original PNG: `715d52a3-0f49-49c1-9fe1-b6733ea89145.png`, 1254×1254 RGBA.
  SHA256 `3f4476174968ab0285a0b478600187ed57092940c664172424435f9468538c46`.
- Original ICO: `download.ico`, frames16/24/32/48/64/128/256.
  SHA256 `aa1f33584830240ba3dc8d619fd6a04febe50c586799c5c2474a1211e593c621`.
- `assets/branding/quartz-q.png` and `quartz-q.ico` are exact byte copies.
  The supplied ICO256 and the PNG downsampled to256 matched every RGBA channel.
  No generated replacement logo, recoloring, cropping or upscaling was used.
- `quartz-q-48.png` is a mechanically decoded ICO frame for the custom titlebar.

## Inspection / integration

- PASS: native-size sheet inspected at16/32/48/128/256. At16, crystal facets are
  necessarily reduced, but the Q silhouette and tail remain identifiable.
  See `assets/branding/icon-sizes-review.png`.
- PASS: six initial asset/header checks; two Windows shell-link safety tests added.
  An initial read-only COM property-store update failed in the disposable test.
  It was corrected to commit on a writable temporary copy before atomic replacement;
  all eight branding tests passed. No original shortcut was modified by that failure.
- Window icon uses `core/branding.py`; custom titlebar embeds the local48px mark.
- PyInstaller uses the supplied ICO; verifier now compares actual RT_ICON payloads
  and copies against it, not just filenames. Inno Setup explicitly requires this Q.
- Shortcut delivery targets only this checkout's EXE. It backs up existing links,
  sets Q icon and `AliMehdi.Quartz.Workspace`, reads back, then atomically replaces.
  Unrelated shortcuts, startup choices, registry, icon cache and pinned items are untouched.

## Build / runtime evidence

Package root: `C:/Users/LENAVO/.codex/backups/quartz-workspace-package-20261021-090500`.

| Acceptance | Result | Evidence |
|---|---|---|
| Full source regression | PASS:267 tests,32.113s | `regression-final.log` in package root |
| Official supplied Q in EXE resources | PASS: all seven payloads match | `package-verification.json`, `exe_q_icon_matches_supplied=true` |
| Native window / titlebar asset wiring | PASS source/built; titlebar graphic LIVE AX | Real packaged process8520, start09:11:07, window1442274; AX entry `16 grafik Quartz Q` |
| Desktop shortcut | PASS file/readback | Existing `Desktop/Quartz - Kısayol.lnk` updated, original backed up; same target, new Q icon and correct AppUserModelID |
| Start menu shortcut | PASS file/readback | Created `Programs/Quartz/Quartz.lnk`, same EXE and Q icon; receipt under `shortcut-backups/shortcut-receipt.json` |
| Native-window/taskbar/shortcut visual rendering | BLOCKED / NOT VERIFIED | Initial `FrameArrived timed out`; fresh window/AX selection plus one Tab focus refresh followed by `window capture timed out`. No further retries or safety bypass |
| Inno setup icon | SOURCE configured; compile NOT VERIFIED | Required Q path, matching AppUserModelID and explicit EXE shortcut icons. Compiler not found on PATH/inspected standard locations; installer not executed |
| Data preservation | PASS | Deployment receipt says all copied data equal. Root env/memory/conversations and distributed env/conversations still equal after live launch/normal close |

Final EXE:
`C:/Users/LENAVO/Desktop/Jarvis config/dist/Quartz/Quartz.exe`.
SHA256 `ddb9c01afa44ab24fc72f990ea619c8271c2ee0605679c77b6f25bef58a971ac`.
Previous complete distribution:
`C:/Users/LENAVO/.codex/backups/quartz-before-desktop-bridge-20261021-091009`.

The packaged app opened successfully, exposed online state and the Q image in AX,
then was closed by normal Alt+F4. Final process check found no Quartz process.
Source asset originals remained unchanged. No chat message or desktop grant was
submitted in this live icon check. Earlier coordination tests are historical and
were not unnecessarily repeated for an artwork-only change.

An existing optional `dist/Quartz/README.txt` installer dependency was absent.
Only that documentation entry now uses `skipifsourcedoesntexist`; mandatory
binary/resource/icon dependencies are not skipped. Reference:
https://jrsoftware.org/ishelp/topic_filessection.htm . This is not a claim that
the unexecuted installer has compiled successfully.

Pre-change checkpoint:
`C:/Users/LENAVO/.codex/backups/quartz-before-q-branding-20261021/agent-1792562454-7fedd18766544985bcc71ee5b768f732.zip`.

No Warband source, save, launch or system setting is part of this continuation.
