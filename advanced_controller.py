"""
advanced_controller.py  —  Quartz
Deep system control — browser automation, VS Code,
media, YouTube, Spotify and more.
Fixed:
  - Discord path corrected
  - smart_open() search depth limited
  - vscode_create_and_run uses clipboard paste
    for special characters
"""

import os
import sys
import time
import subprocess
import platform
import webbrowser
import urllib.parse
import urllib.request
import re
import json
import pyperclip
from difflib import SequenceMatcher
from pathlib import Path
from itertools import islice
from typing import Optional

from logger import get_logger

log = get_logger(__name__)
QUARTZ_POWER_PLAN_NAME = "Quartz Sessiz Uzaktan Erişim"
QUARTZ_POWER_PLAN_MATCH = "Quartz Sessiz Uzaktan"

# ── Selenium (optional) ───────────────────────────────────────────────────────
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import (
        WebDriverWait)
    from selenium.webdriver.support import (
        expected_conditions as EC)
    from selenium.webdriver.chrome.options import (
        Options as ChromeOptions)
    from selenium.webdriver.chrome.service import (
        Service)
    from webdriver_manager.chrome import (
        ChromeDriverManager)
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False
    log.warning(
        "Selenium not installed — "
        "browser automation disabled")

# ── pyautogui ─────────────────────────────────────────────────────────────────
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

# ── pycaw (Windows volume) ────────────────────────────────────────────────────
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import (
        AudioUtilities, IAudioEndpointVolume)
    PYCAW_OK = True
except ImportError:
    PYCAW_OK = False


# ─────────────────────────────────────────────────────────────────────────────
#  YouTube
# ─────────────────────────────────────────────────────────────────────────────

def youtube_play(query: str) -> str:
    """
    Resolve the first YouTube result, then open it in the user's normal browser.
    This preserves the signed-in Chrome profile instead of creating a fresh
    Selenium browser profile.
    """
    log.info("youtube_play: %s", query)
    search_url = (
        "https://www.youtube.com/results?search_query="
        + urllib.parse.quote(query)
    )
    try:
        request = urllib.request.Request(
            search_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            page = response.read().decode("utf-8", errors="ignore")
        video_id = _extract_youtube_video_id(page)
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
            _open_in_user_browser(url)
            return f"Playing on YouTube: '{query}'"
    except Exception as exc:
        log.warning("YouTube result resolution failed: %s", exc)

    _open_in_user_browser(search_url)
    return f"Opened YouTube search for '{query}'"


def _extract_youtube_video_id(page: str) -> Optional[str]:
    """Return the first video id from a YouTube results document."""
    match = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', page)
    return match.group(1) if match else None


def _open_in_user_browser(url: str) -> None:
    """Open a URL through Windows so the existing signed-in profile is reused."""
    if platform.system() == "Windows":
        os.startfile(url)
    else:
        webbrowser.open(url)


def _youtube_selenium(query: str) -> str:
    """Open YouTube, search, click first video."""
    try:
        opts = ChromeOptions()
        opts.add_argument("--start-maximized")
        opts.add_experimental_option(
            "excludeSwitches", ["enable-logging"])

        driver = webdriver.Chrome(
            service=Service(
                ChromeDriverManager().install()),
            options=opts,
        )

        driver.get("https://www.youtube.com")
        wait = WebDriverWait(driver, 10)

        # Accept cookies if prompted
        try:
            accept = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH,
                     "//button[contains(.,"
                     " 'Accept')]")))
            accept.click()
            time.sleep(1)
        except Exception:
            pass

        # Search
        search_box = wait.until(
            EC.presence_of_element_located(
                (By.NAME, "search_query")))
        search_box.clear()
        search_box.send_keys(query)
        search_box.send_keys(Keys.RETURN)
        time.sleep(2)

        # Click first video result
        first_video = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 "ytd-video-renderer "
                 "a#video-title")))
        title = first_video.text
        first_video.click()

        return (
            f"Playing on YouTube: '{title}'\n"
            f"Search query: '{query}'"
        )

    except Exception as exc:
        log.exception("YouTube selenium error")
        url = (
            "https://www.youtube.com/results"
            "?search_query="
            + urllib.parse.quote(query)
        )
        webbrowser.open(url)
        return (
            f"Opened YouTube search for '{query}'.\n"
            f"Auto-click failed: {exc}"
        )


def youtube_search(query: str) -> str:
    """Open YouTube search results page."""
    url = (
        "https://www.youtube.com/results"
        "?search_query="
        + urllib.parse.quote(query)
    )
    _open_in_user_browser(url)
    return f"Opened YouTube search: '{query}'"


# ─────────────────────────────────────────────────────────────────────────────
#  Spotify
# ─────────────────────────────────────────────────────────────────────────────

def spotify_play(query: str) -> str:
    """Open Spotify and search for a track."""
    log.info("spotify_play: %s", query)
    try:
        uri = (
            "spotify:search:"
            + urllib.parse.quote(query)
        )
        if platform.system() == "Windows":
            os.startfile(uri)
        else:
            subprocess.Popen(["xdg-open", uri])

        time.sleep(2)
        if PYAUTOGUI_OK:
            time.sleep(3)
            pyautogui.hotkey("enter")

        return (
            f"Spotify opened with search: '{query}'"
        )
    except Exception as exc:
        log.exception("Spotify play error")
        url = (
            "https://open.spotify.com/search/"
            + urllib.parse.quote(query)
        )
        webbrowser.open(url)
        return (
            f"Opened Spotify web search: '{query}'"
        )


def spotify_control(action: str) -> str:
    """Control Spotify playback."""
    log.info("spotify_control: %s", action)
    if not PYAUTOGUI_OK:
        return (
            "pyautogui not installed — "
            "cannot control Spotify"
        )

    controls = {
        "play":     ["space"],
        "pause":    ["space"],
        "next":     ["ctrl", "right"],
        "previous": ["ctrl", "left"],
        "stop":     ["space"],
    }
    keys = controls.get(action.lower())
    if not keys:
        return f"Unknown action: {action}"

    if platform.system() == "Windows":
        subprocess.run(
            ['powershell', '-NoProfile', '-Command',
            '(New-Object -ComObject '
            'Shell.Application).Windows() | '
            'Where-Object {$_.Name -eq '
            "\'Spotify\'} | "
            'ForEach-Object '
            '{$_.Visible=$true}'],
            shell=False,
        )
        time.sleep(0.5)

    pyautogui.hotkey(*keys)
    return f"Spotify: {action}"


# ─────────────────────────────────────────────────────────────────────────────
#  VS Code
# ─────────────────────────────────────────────────────────────────────────────

def vscode_open_file(filepath: str) -> str:
    """Open a file in VS Code."""
    log.info("vscode_open_file: %s", filepath)
    try:
        subprocess.Popen(["code", filepath], shell=False)
        return f"Opened in VS Code: {filepath}"
    except Exception as exc:
        return f"Error opening VS Code: {exc}"


def vscode_open_folder(folder: str) -> str:
    """Open a folder in VS Code."""
    log.info("vscode_open_folder: %s", folder)
    try:
        subprocess.Popen(["code", folder], shell=False)
        return f"Opened folder in VS Code: {folder}"
    except Exception as exc:
        return f"Error: {exc}"


def vscode_create_and_run(
        language: str,
        code: str,
        filename: str = None) -> str:
    """
    Create a code file, open in VS Code,
    run in integrated terminal.
    Fixed: uses clipboard paste for special chars.
    """
    log.info(
        "vscode_create_and_run: "
        "lang=%s file=%s", language, filename)

    ext_map = {
        "python":     ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "html":       ".html",
        "css":        ".css",
        "java":       ".java",
        "cpp":        ".cpp",
        "c":          ".c",
        "rust":       ".rs",
        "go":         ".go",
        "ruby":       ".rb",
        "php":        ".php",
    }
    ext = ext_map.get(language.lower(), ".py")

    if not filename:
        filename = "quartz_code" + ext

    if not any(filename.endswith(e)
               for e in ext_map.values()):
        filename = filename + ext

    desktop  = Path.home() / "Desktop"
    filepath = desktop / filename

    code = code.replace("\\n", "\n")
    code = code.replace("\\t", "\t")

    try:
        filepath.write_text(
            code, encoding="utf-8")
        log.info("Code written to %s", filepath)
    except Exception as exc:
        return f"Error writing file: {exc}"

    try:
        subprocess.Popen(["code", str(filepath)], shell=False)
        time.sleep(3)

        if PYAUTOGUI_OK:
            # Open terminal
            pyautogui.hotkey("ctrl", "grave")
            time.sleep(1.5)

            run_cmd = _get_run_command(
                language, str(filepath))

            # ── Use clipboard paste instead of
            #    pyautogui.write() to handle
            #    special characters safely ────────
            pyperclip.copy(run_cmd)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")

        return (
            f"Created: {filepath}\n"
            f"Opened in VS Code\n"
            f"Running: "
            f"{_get_run_command(language, filename)}"
        )
    except Exception as exc:
        return (
            f"File created at {filepath}\n"
            f"VS Code error: {exc}"
        )


def _get_run_command(
        language: str, filepath: str) -> str:
    cmds = {
        "python":     f'python "{filepath}"',
        "javascript": f'node "{filepath}"',
        "typescript": f'ts-node "{filepath}"',
        "java":       (
            f'javac "{filepath}" && java Main'),
        "cpp":        (
            f'g++ "{filepath}" -o out && ./out'),
        "c":          (
            f'gcc "{filepath}" -o out && ./out'),
        "rust":       (
            f'rustc "{filepath}" && ./main'),
        "go":         f'go run "{filepath}"',
        "ruby":       f'ruby "{filepath}"',
        "php":        f'php "{filepath}"',
    }
    return cmds.get(
        language.lower(),
        f'python "{filepath}"',
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Volume control
# ─────────────────────────────────────────────────────────────────────────────

def set_volume(level: int) -> str:
    """Set system volume 0-100."""
    log.info("set_volume: %d", level)
    level = max(0, min(100, level))

    if PYCAW_OK:
        try:
            devices = AudioUtilities.GetSpeakers()
            iface   = devices.Activate(
                IAudioEndpointVolume._iid_,
                CLSCTX_ALL, None)
            volume  = cast(
                iface,
                POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(
                level / 100.0, None)
            return f"Volume set to {level}%"
        except Exception as exc:
            log.warning("pycaw failed: %s", exc)

    if platform.system() == "Windows":
        try:
            subprocess.run(
                ["nircmd", "setsysvolume", str(int(level * 655.35))],
                shell=False, check=True,
            )
            return f"Volume set to {level}%"
        except Exception:
            pass

        try:
            ps = (
                f"$wshShell = "
                "new-object -com wscript.shell;"
                f"$vol = {level};"
            )
            subprocess.run(
                ["powershell", "-command", ps],
                capture_output=True,
            )
            return (
                f"Volume set to "
                f"approximately {level}%"
            )
        except Exception as exc:
            return f"Error setting volume: {exc}"

    return (
        f"Volume control not supported "
        f"on {platform.system()}"
    )


def get_volume() -> str:
    """Get current system volume."""
    if PYCAW_OK:
        try:
            devices = AudioUtilities.GetSpeakers()
            iface   = devices.Activate(
                IAudioEndpointVolume._iid_,
                CLSCTX_ALL, None)
            volume  = cast(
                iface,
                POINTER(IAudioEndpointVolume))
            level   = round(
                volume.GetMasterVolumeLevelScalar()
                * 100)
            return f"Current volume: {level}%"
        except Exception as exc:
            return f"Error getting volume: {exc}"
    return "Volume control not available"


def mute_volume() -> str:
    """Mute system volume."""
    if PYAUTOGUI_OK:
        pyautogui.press("volumemute")
        return "Volume muted"
    return "Cannot mute — pyautogui not installed"


# ─────────────────────────────────────────────────────────────────────────────
#  Browser control
# ─────────────────────────────────────────────────────────────────────────────

def browser_open_url(url: str) -> str:
    """Open a URL in the default browser."""
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened: {url}"


def google_search(query: str) -> str:
    """Search Google."""
    url = (
        "https://www.google.com/search?q="
        + urllib.parse.quote(query)
    )
    webbrowser.open(url)
    return f"Google search: '{query}'"


# ─────────────────────────────────────────────────────────────────────────────
#  Windows system actions
# ─────────────────────────────────────────────────────────────────────────────

def system_shutdown(delay: int = 0) -> str:
    """Shutdown the computer."""
    log.info("system_shutdown delay=%d", delay)
    if platform.system() == "Windows":
        subprocess.run(["shutdown", "/s", "/t", str(delay)], shell=False)
        return f"Shutting down in {delay} seconds"
    subprocess.run(["shutdown", "-h", "now"])
    return "Shutting down"


def system_restart(delay: int = 0) -> str:
    """Restart the computer."""
    log.info("system_restart delay=%d", delay)
    if platform.system() == "Windows":
        subprocess.run(["shutdown", "/r", "/t", str(delay)], shell=False)
        return f"Restarting in {delay} seconds"
    return "Restart not supported"


def system_sleep() -> str:
    """Put the computer to sleep."""
    log.info("system_sleep")
    if platform.system() == "Windows":
        subprocess.run(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            shell=False)
        return "Going to sleep"
    return "Sleep not supported"


def quartz_mode() -> str:
    """Enable Quartz's low-noise, always-online power profile on Windows."""
    if platform.system() != "Windows":
        return "Quartz Mode is only available on Windows."

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["powercfg", "/list"], capture_output=True,
            check=True, creationflags=flags)
        raw_listing = result.stdout or b""
        listed = (raw_listing.decode(errors="replace")
                  if isinstance(raw_listing, bytes) else str(raw_listing))
        line = next((entry for entry in listed.splitlines()
                     if QUARTZ_POWER_PLAN_MATCH.casefold() in entry.casefold()), None)
        match = re.search(
            r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
            line or "")
        if not match:
            return "Quartz Mode güç planı bulunamadı."
        subprocess.run(
            ["powercfg", "/setactive", match.group(0)], check=True,
            creationflags=flags)
        log.info("Quartz Mode enabled: %s", match.group(0))
        return ("Quartz Mode etkin: ekran kapanacak; Quartz, Wi-Fi ve "
                "uzaktan erişim açık kalacak.")
    except (OSError, subprocess.CalledProcessError) as exc:
        log.warning("Quartz Mode could not be enabled: %s", exc)
        return f"Quartz Mode etkinleştirilemedi: {exc}"


def lock_screen() -> str:
    """Lock the screen."""
    log.info("lock_screen")
    if platform.system() == "Windows":
        subprocess.run(
            ["rundll32.exe", "user32.dll,LockWorkStation"], shell=False)
        return "Screen locked"
    return "Lock not supported"


def empty_recycle_bin() -> str:
    """Empty the recycle bin."""
    log.info("empty_recycle_bin")
    if platform.system() == "Windows":
        try:
            import winshell
            winshell.recycle_bin().empty(
                confirm=False,
                show_progress=False,
                sound=False,
            )
            return "Recycle bin emptied"
        except ImportError:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Clear-RecycleBin -Force"], shell=False)
            return "Recycle bin emptied"
    return "Not supported"


# ─────────────────────────────────────────────────────────────────────────────
#  App launcher (smart) — fixed search depth
# ─────────────────────────────────────────────────────────────────────────────

def _find_discord_path() -> Optional[str]:
    """Find the actual Discord executable."""
    local = Path(
        os.environ.get("LOCALAPPDATA", ""))
    matches = sorted(
        local.glob("Discord/app-*/Discord.exe"))
    if matches:
        return str(matches[-1])
    return None


def _search_dir_limited(
        directory: Path,
        pattern: str,
        name_lower: str,
        max_items: int = 200,
) -> Optional[Path]:
    """
    Search a directory for a matching file
    with a hard limit on items checked.
    Prevents 30-second hangs on large dirs.
    """
    try:
        candidates = (
            f for f in directory.rglob(pattern)
            if name_lower in f.stem.lower()
        )
        return next(
            islice(candidates, max_items), None)
    except Exception:
        return None


def smart_open(app_name: str) -> str:
    """
    Intelligently open any app by name.
    Fixed: Discord path + limited search depth.
    """
    log.info("smart_open: %s", app_name)
    name_lower = app_name.lower().strip()

    # Tool-capable models can occasionally send a website to smart_open.
    # Resolve known sites before searching Windows applications. On Windows,
    # os.startfile keeps the user's default, signed-in browser profile.
    websites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "netflix": "https://www.netflix.com",
        "twitch": "https://www.twitch.tv",
        "instagram": "https://www.instagram.com",
        "facebook": "https://www.facebook.com",
        "linkedin": "https://www.linkedin.com",
        "reddit": "https://www.reddit.com",
    }
    for site, url in websites.items():
        if site in name_lower:
            _open_in_user_browser(url)
            return f"Opened website: {site}"

    # ── Built-in Windows commands ─────────────────────────
    builtin = {
        "notepad":        "notepad",
        "calculator":     "calc",
        "paint":          "mspaint",
        "wordpad":        "wordpad",
        "cmd":            "cmd",
        "powershell":     "powershell",
        "task manager":   "taskmgr",
        "control panel":  "control",
        "settings":       "ms-settings:",
        "file explorer":  "explorer",
        "snipping tool":  "snippingtool",
        "magnifier":      "magnify",
        "narrator":       "narrator",
        "regedit":        "regedit",
        "msconfig":       "msconfig",
        "disk cleanup":   "cleanmgr",
        "device manager": "devmgmt.msc",
    }

    if name_lower in builtin:
        cmd = builtin[name_lower]
        if cmd.startswith("ms-"):
            os.startfile(cmd)
        else:
            subprocess.Popen([cmd], shell=False)
        return f"Opened {app_name}"

    # ── Common apps (fixed Discord path) ─────────────────
    discord_path = _find_discord_path()
    username     = os.getenv("USERNAME", "")

    common = {
        "chrome": (
            r"C:\Program Files\Google\Chrome"
            r"\Application\chrome.exe"),
        "firefox": (
            r"C:\Program Files\Mozilla Firefox"
            r"\firefox.exe"),
        "steam": (
            r"C:\Program Files (x86)\Steam"
            r"\steam.exe"),
        "discord": discord_path or "",
        "spotify": os.path.expandvars(
            r"%APPDATA%\Spotify\Spotify.exe"),
        "vscode": (
            rf"C:\Users\{username}\AppData\Local"
            r"\Programs\Microsoft VS Code"
            r"\Code.exe"),
        "code": (
            rf"C:\Users\{username}\AppData\Local"
            r"\Programs\Microsoft VS Code"
            r"\Code.exe"),
        "teams": os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\Teams"
            r"\current\Teams.exe"),
        "obs": (
            r"C:\Program Files\obs-studio"
            r"\bin\64bit\obs64.exe"),
        "vlc": (
            r"C:\Program Files\VideoLAN"
            r"\VLC\vlc.exe"),
        "7zip": (
            r"C:\Program Files\7-Zip\7zFM.exe"),
        "winrar": (
            r"C:\Program Files\WinRAR"
            r"\WinRAR.exe"),
        "throttlestop": os.path.expandvars(
            r"%USERPROFILE%\Desktop"
            r"\ThrottleStop\ThrottleStop.exe"),
    }

    for key, path in common.items():
        if key in name_lower and path:
            if os.path.exists(path):
                subprocess.Popen([path], shell=False)
                return (
                    f"Opened {app_name} "
                    f"from {path}")

    # ── Targeted search (limited depth) ──────────────────
    search_dirs = [
        Path.home() / "Desktop",
        Path(
            r"C:\ProgramData\Microsoft\Windows"
            r"\Start Menu\Programs"),
        Path.home() / "AppData" / "Roaming"
        / "Microsoft" / "Windows"
        / "Start Menu",
    ]

    for directory in search_dirs:
        if not directory.exists():
            continue

        # Search .lnk shortcuts first (faster)
        found = _search_dir_limited(
            directory, "*.lnk",
            name_lower, max_items=100)
        if found:
            os.startfile(str(found))
            return f"Opened shortcut: {found.stem}"

        # Search .exe files
        found = _search_dir_limited(
            directory, "*.exe",
            name_lower, max_items=100)
        if found:
            subprocess.Popen([str(found)], shell=False)
            return f"Found and opened: {found}"

    # ── Last resort ───────────────────────────────────────
    try:
        os.startfile(app_name)
        return f"Attempted to open: {app_name}"
    except Exception as exc:
        return (
            f"Could not find or open: "
            f"{app_name} — {exc}"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Steam direct control
# ─────────────────────────────────────────────────────────────────────────────

def steam_open_library() -> str:
    """Open the signed-in Steam client's Library without screen clicking."""
    if platform.system() != "Windows":
        raise RuntimeError("Steam URI control currently requires Windows")
    os.startfile("steam://open/games")
    return "Steam Library opened through the signed-in Steam client."


def _steam_game_candidate(game_name: str) -> tuple[int, str]:
    """Resolve a game title through Steam's store search endpoint."""
    query = str(game_name).strip()
    if not query:
        raise ValueError("Game name cannot be empty")
    url = (
        "https://store.steampowered.com/api/storesearch/?cc=TR&l=turkish&term="
        + urllib.parse.quote(query))
    request = urllib.request.Request(url, headers={
        "User-Agent": "Quartz/1.0 desktop assistant"})
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    items = payload.get("items", []) if isinstance(payload, dict) else []
    candidates = [item for item in items[:10]
                  if isinstance(item, dict) and item.get("id") and item.get("name")]
    if not candidates:
        raise LookupError(f"Steam could not find a game named '{query}'")
    wanted = query.casefold()
    best = max(candidates, key=lambda item: SequenceMatcher(
        None, wanted, str(item["name"]).casefold()).ratio())
    score = SequenceMatcher(
        None, wanted, str(best["name"]).casefold()).ratio()
    if score < 0.55:
        raise LookupError(
            f"Steam result was too ambiguous for '{query}' (best: {best['name']})")
    return int(best["id"]), str(best["name"])


def steam_install_game(game_name: str) -> str:
    """Resolve a title and open its official Steam installation dialog."""
    if platform.system() != "Windows":
        raise RuntimeError("Steam URI control currently requires Windows")
    app_id, resolved_name = _steam_game_candidate(game_name)
    os.startfile(f"steam://install/{app_id}")
    return (
        f"Steam installation dialog opened for '{resolved_name}' "
        f"(AppID {app_id}). The signed-in Steam client will verify ownership, "
        "disk location and available space.")


#  Typing & keyboard
# ─────────────────────────────────────────────────────────────────────────────

def type_and_enter(text: str) -> str:
    """Type text and press Enter."""
    if not PYAUTOGUI_OK:
        return "pyautogui not installed"
    time.sleep(0.5)
    pyautogui.write(text, interval=0.04)
    pyautogui.press("enter")
    return f"Typed and pressed Enter: {text}"


def hotkey(keys: str) -> str:
    """
    Press a key combination.
    Example: hotkey('ctrl+c') or hotkey('alt+f4')
    """
    if not PYAUTOGUI_OK:
        return "pyautogui not installed"
    parts = [k.strip() for k in keys.split("+")]
    pyautogui.hotkey(*parts)
    return f"Pressed: {keys}"


# ─────────────────────────────────────────────────────────────────────────────
#  Clipboard
# ─────────────────────────────────────────────────────────────────────────────

def clipboard_copy(text: str) -> str:
    """Copy text to clipboard."""
    try:
        pyperclip.copy(text)
        return f"Copied to clipboard: {text[:50]}"
    except Exception as exc:
        return f"Error: {exc}"


def clipboard_paste() -> str:
    """Get clipboard content."""
    try:
        content = pyperclip.paste()
        return f"Clipboard: {content}"
    except Exception as exc:
        return f"Error: {exc}"
