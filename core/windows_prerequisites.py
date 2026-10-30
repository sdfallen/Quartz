"""WebView2 check before the WebView-based GUI starts. No admin or plan changes."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import threading
import webbrowser

WEBVIEW_DOWNLOAD = "https://developer.microsoft.com/microsoft-edge/webview2/"
BOOTSTRAPPER = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
CLIENT_KEY = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def webview2_status(registry=None):
    if os.name != "nt" and registry is None:
        return {"installed": True, "version": "", "platform": "non-windows"}
    if registry is None:
        import winreg as registry
    for hive in (registry.HKEY_CURRENT_USER, registry.HKEY_LOCAL_MACHINE):
        for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
            try:
                with registry.OpenKey(hive, CLIENT_KEY, 0, registry.KEY_READ | view) as key:
                    version = registry.QueryValueEx(key, "pv")[0]
                parts = str(version).split(".")
                if len(parts) == 4 and all(p.isdigit() for p in parts) and any(int(p) for p in parts):
                    return {"installed": True, "version": str(version)}
            except OSError:
                continue
    return {"installed": False, "version": ""}


def install_webview2():
    from core.install_security import download, verify_publisher
    if webview2_status()["installed"]:
        return {"installed": True, "reused": True}
    with tempfile.TemporaryDirectory(prefix="quartz-webview2-") as temporary:
        binary = download(BOOTSTRAPPER, Path(temporary) / "MicrosoftEdgeWebview2Setup.exe",
                          allowed=[("go.microsoft.com", "/fwlink/"),
                                   ("msedge.sf.dl.delivery.mp.microsoft.com", "/filestreamingservice/")],
                          limit=10 * 1024 * 1024)
        verify_publisher(binary, "Microsoft Corporation")
        result = subprocess.run([str(binary), "/silent", "/install"], timeout=600,
                                capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        status = webview2_status()
        if result.returncode not in (0, 3010) or not status["installed"]:
            raise RuntimeError("WebView2 kurulumu doğrulanamadı. İnternet bağlantısını kontrol edip yeniden deneyin.")
        return {**status, "reused": False}


def ensure_webview2():
    """A native dialog works even when WebView2 is absent; never start backend early."""
    if webview2_status()["installed"]:
        return True
    import tkinter as tk
    from tkinter import messagebox, ttk
    root = tk.Tk()
    root.withdraw()
    try:
        if not messagebox.askyesno("Quartz — İlk kurulum",
                "Quartz arayüzü için Microsoft WebView2 gerekli.\n\n"
                "Resmî Microsoft kurucusu indirilip bu kullanıcı için çalıştırılsın mı? "
                "Yönetici izni istenmez. İnternet gerekir.", parent=root):
            if messagebox.askyesno("Quartz — WebView2", "Resmî indirme sayfası açılsın mı?", parent=root):
                webbrowser.open(WEBVIEW_DOWNLOAD)
            return False
        root.title("Quartz — WebView2 hazırlanıyor")
        root.geometry("460x130")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(root, text="Microsoft WebView2 indiriliyor ve doğrulanıyor…\n"
                  "Kurulum birkaç dakika sürebilir.", padding=16).pack()
        bar = ttk.Progressbar(root, mode="indeterminate")
        bar.pack(fill="x", padx=16); bar.start()
        result = {}
        def work():
            try:
                result["ok"] = install_webview2()["installed"]
            except Exception:
                result["ok"] = False
            finally:
                result["done"] = True
        def poll():
            if not result.get("done"):
                root.after(100, poll)
            else:
                root.quit()
        threading.Thread(target=work, daemon=True, name="quartz-webview-install").start()
        root.deiconify(); root.after(100, poll); root.mainloop()
        if not result.get("ok"):
            messagebox.showerror("Quartz — Kurulum tamamlanamadı",
                                 "WebView2 kurulamadı veya doğrulanamadı. Quartz'ı yeniden açarak "
                                 "tekrar deneyebilir ya da resmî Microsoft sayfasından kurabilirsiniz.", parent=root)
            webbrowser.open(WEBVIEW_DOWNLOAD)
        return bool(result.get("ok"))
    finally:
        root.destroy()
