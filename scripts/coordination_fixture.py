"""Owned disposable UI + genuine callback/heartbeat log, no external IO."""
import json
import os
from pathlib import Path
import threading
import time
import webview
from desktop_acceptance_fixture import HTML

ROOT = Path(os.environ["QUARTZ_FIXTURE_DIR"]).resolve(strict=True)
LOCK = threading.Lock()


def event(kind, **data):
    with LOCK, (ROOT/"events.jsonl").open("a",encoding="utf-8") as stream:
        stream.write(json.dumps({"event":kind,"timestamp":time.time(),**data})+"\n")


class Api:
    def record(self,text,count):
        event("button_callback",text=text,click_count=count)
        (ROOT/"callback.json").write_text(json.dumps({"text":text,"click_count":count}),encoding="utf-8")


def heartbeat():
    for number in range(180):
        event("heartbeat",sequence=number)
        time.sleep(1)


if __name__=="__main__":
    event("fixture_ready",pid=os.getpid())
    threading.Thread(target=heartbeat,daemon=True).start()
    webview.create_window("Quartz Disposable Coordination Test",html=HTML,js_api=Api(),width=850,height=550)
    webview.start()
