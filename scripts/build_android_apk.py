"""Build the SpeS Android app (android/) into a signed APK outside the repository.

Toolchain and the release key live only on this computer, under
%LOCALAPPDATA%\\SpeS-dev (jdk17, android-sdk, gradle-8.10.2, signing/). The key is
created once with a random password stored next to it; neither is committed.
Output: %LOCALAPPDATA%\\SpeS-dev\\out\\SpeS-<version>.apk
"""
import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"


def dev_root() -> Path:
    # Not under AppData: the Microsoft Store Python sees a virtualised AppData and would miss it.
    return Path(os.environ.get("SPES_DEV_ROOT") or Path.home() / ".spes-dev")


def toolchain(root: Path) -> dict:
    jdk, sdk = root / "jdk17", root / "android-sdk"
    gradle = next(iter(sorted(root.glob("gradle-*/bin/gradle.bat"))), None)
    missing = [str(p) for p in (jdk / "bin/java.exe", sdk / "platforms") if not p.exists()]
    if gradle is None:
        missing.append(str(root / "gradle-*/bin/gradle.bat"))
    if missing:
        raise SystemExit("Android araçları eksik: " + ", ".join(missing))
    return {"jdk": jdk, "sdk": sdk, "gradle": gradle}


def signing(root: Path, jdk: Path) -> tuple[Path, str]:
    folder = root / "signing"
    store, info = folder / "spes-release.jks", folder / "spes-release.json"
    if store.exists() and info.exists():
        return store, json.loads(info.read_text(encoding="utf-8"))["password"]
    folder.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(24)
    subprocess.run([str(jdk / "bin/keytool.exe"), "-genkeypair", "-keystore", str(store), "-alias", "spes",
                    "-keyalg", "RSA", "-keysize", "3072", "-validity", "9125", "-storepass", password,
                    "-keypass", password, "-dname", "CN=SpeS Mobile"], check=True, capture_output=True)
    info.write_text(json.dumps({"password": password, "note": "SpeS APK imza anahtari; paylasmayin"}), encoding="utf-8")
    return store, password


def version() -> str:
    text = (ANDROID / "app/build.gradle.kts").read_text(encoding="utf-8")
    return re.search(r'versionName = "([^"]+)"', text).group(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="debug APK, without the release key")
    args = parser.parse_args()
    root = dev_root()
    tools = toolchain(root)
    env = dict(os.environ, JAVA_HOME=str(tools["jdk"]), ANDROID_HOME=str(tools["sdk"]),
               ANDROID_SDK_ROOT=str(tools["sdk"]), GRADLE_USER_HOME=str(root / "gradle-home"))
    env["PATH"] = str(tools["jdk"] / "bin") + os.pathsep + env.get("PATH", "")
    task = "assembleDebug" if args.debug else "assembleRelease"
    if not args.debug:
        store, password = signing(root, tools["jdk"])
        env.update(SPES_KEYSTORE=str(store), SPES_KEYSTORE_PASSWORD=password)
    result = subprocess.run([str(tools["gradle"]), "--no-daemon", "-q", "-p", str(ANDROID), task], env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
    kind = "debug" if args.debug else "release"
    built = ANDROID / f"app/build/outputs/apk/{kind}/app-{kind}.apk"
    out = root / "out"
    out.mkdir(exist_ok=True)
    target = out / f"SpeS-{version()}{'-debug' if args.debug else ''}.apk"
    shutil.copy2(built, target)
    print(json.dumps({"apk": str(target), "bytes": target.stat().st_size, "signed_with": "release key" if not args.debug else "debug key"}))


if __name__ == "__main__":
    sys.exit(main())
