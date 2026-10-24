"""Disposable classic Windows controls. No network, game or user documents."""
import json
from pathlib import Path
import pythoncom
pythoncom.CoInitialize()
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
from System.Windows.Forms import Application, Form, Label, TextBox, Button
from System.Drawing import Point, Size

STATE = Path(__file__).resolve().parents[1] / "labs/desktop-bridge-20261020/native-fixture-state.json"

form = Form()
form.Text = "Quartz Disposable Desktop Test"
form.Size = Size(850, 550)

def label(text, x, y, width=750):
    item = Label(); item.Text = text; item.Location = Point(x, y); item.Size = Size(width, 35)
    form.Controls.Add(item)
    return item

label("Classic Windows desktop acceptance - no game or user documents", 25, 25)
label("Visual challenge number: 4826", 25, 85)
label("Test text:", 25, 150, 120)
entry = TextBox(); entry.AccessibleName = "Test text"; entry.Location = Point(160, 150); entry.Size = Size(350, 40)
form.Controls.Add(entry)
button = Button(); button.Text = "TEST BUTTON"; button.Location = Point(280, 250); button.Size = Size(200, 70)
form.Controls.Add(button)
result = label("Clicks: 0", 25, 370)
count = 0

def clicked(sender, event):
    global count
    count += 1
    result.Text = "Clicks: " + str(count) + " | Text: " + str(entry.Text)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"text": str(entry.Text), "click_count": count, "fixture": "classic-winforms"}), encoding="utf-8")

button.Click += clicked
Application.Run(form)
