"""Disposable visual UI for desktop-operator acceptance. No network or user files.

This is deliberately not a game fixture and cannot prove Warband acceptance.
"""
import json
from pathlib import Path
import webview

STATE = Path(__file__).resolve().parents[1] / "labs" / "desktop-bridge-20261020" / "native-fixture-state.json"


class Api:
    def record(self, text, count):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"text": text, "click_count": count}), encoding="utf-8")


HTML = """<!doctype html><html><body style="font:22px sans-serif;background:#142536;color:white;padding:28px">
<h2>Quartz Disposable Desktop Test</h2><p>No game, no user documents, no external network.</p>
<p>Visual challenge number: <b>4826</b></p>
<label for="entry">Test text: </label><input id="entry" aria-label="Test text" style="font-size:24px;width:340px" />
<button id="test" style="display:block;margin:35px 0 0 260px;padding:20px;font-size:22px">TEST BUTTON</button>
<p id="result">Clicks: 0</p>
<script>let count=0;document.getElementById('test').onclick=async()=>{
count++;const text=document.getElementById('entry').value;
document.getElementById('result').textContent=`Clicks: ${count} | Text: ${text}`;
await window.pywebview.api.record(text,count);};</script></body></html>"""


if __name__ == "__main__":
    webview.create_window("Quartz Disposable Desktop Test", html=HTML, js_api=Api(), width=850, height=550)
    webview.start()
