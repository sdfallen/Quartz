"""Disposable test window for the live Görev Sınavı (no network, no user files).

The host passes where its state goes; the window only records what it received:
the current text, the click count, an event sequence (text at each click, then
"click") and a timestamped log of every input change. The state file belongs to
the host's oracle folder, outside the fixture the agents can write to.

    python -B scripts/exam_fixture_app.py --state <host>/fixture-state.json
"""
import argparse
import json
import os
from pathlib import Path
import time

import webview

TITLE = "Quartz Sinav Test Uygulamasi"


class Api:
    def __init__(self, state: Path):
        self.state = state
        self.data = {"text": "", "click_count": 0, "events": [], "inputs": [], "pid": os.getpid(), "started": time.time()}
        self._write()

    def _write(self):
        temporary = self.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.state)

    def typed(self, text):
        text = str(text)[:2000]
        self.data["text"] = text
        if len(self.data["inputs"]) < 2000:
            self.data["inputs"].append({"at": time.time(), "length": len(text)})
        self._write()

    def clicked(self, text):
        text = str(text)[:2000]
        self.data["text"] = text
        self.data["click_count"] += 1
        self.data["events"] += [text, "click"]
        self.data["last_click_at"] = time.time()
        self._write()


HTML = """<!doctype html><html><head><meta charset="utf-8"></head>
<body style="font:20px 'Segoe UI',sans-serif;background:#16202e;color:#f2f4f8;padding:26px">
<h2 style="margin:0 0 6px">Quartz Sinav Test Uygulamasi</h2>
<p style="margin:0 0 22px;color:#aab4c4">Tek kullanimlik test penceresi. Ag yok, kullanici dosyasi yok.</p>
<label for="entry">Test metni: </label>
<input id="entry" aria-label="Test metni" style="font-size:22px;width:420px" autocomplete="off" />
<button id="test" style="display:block;margin:30px 0 0 0;padding:16px 26px;font-size:20px">TEST BUTTON</button>
<p id="result">Tiklama: 0</p>
<script>
let count=0;const entry=document.getElementById('entry');
entry.addEventListener('input',()=>window.pywebview.api.typed(entry.value));
document.getElementById('test').onclick=async()=>{count++;
  document.getElementById('result').textContent=`Tiklama: ${count} | Metin: ${entry.value}`;
  await window.pywebview.api.clicked(entry.value);};
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    args = parser.parse_args()
    state = Path(args.state).resolve()
    state.parent.mkdir(parents=True, exist_ok=True)
    webview.create_window(TITLE, html=HTML, js_api=Api(state), width=760, height=440)
    webview.start()


if __name__ == "__main__":
    main()
