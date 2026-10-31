"""Keyboard access cannot submit on focus, composition or key auto-repeat."""
import subprocess
import unittest
import gui


class ChatKeyboardTests(unittest.TestCase):
    def test_focus_and_submit_respect_modal_and_input_boundaries(self):
        start = gui._HTML.index('  // Keyboard access remains available')
        end = gui._HTML.index("  document.querySelectorAll('.qa-btn", start)
        script = r'''
const assert = require('node:assert/strict');
const handlers = {};
let modal = false, focused = 0, sent = 0;
const document = {addEventListener: (_, fn) => handlers.global=fn,
 querySelectorAll: () => modal ? [{getClientRects: () => [1]}] : []};
const inputEl = {disabled:false,getClientRects:()=>[1], focus:()=>focused++,
 addEventListener:(_, fn)=>handlers.input=fn};
const inpHistory=[]; let histCursor=-1;
function sendAgentMessage() {sent++;}
''' + gui._HTML[start:end] + r'''
function key(extra={}) {return {key:'l',ctrlKey:true,preventDefault(){this.prevented=true},...extra};}
handlers.global(key()); assert.equal(focused,1); assert.equal(sent,0);
modal=true; handlers.global(key()); assert.equal(focused,1);
modal=false; inputEl.disabled=true; handlers.global(key()); assert.equal(focused,1);
inputEl.disabled=false; handlers.global(key({altKey:true})); assert.equal(focused,1);
handlers.input(key({key:'Enter',isComposing:true})); assert.equal(sent,0);
handlers.input(key({key:'Enter',repeat:true})); assert.equal(sent,0);
handlers.input(key({key:'Enter'})); assert.equal(sent,1);
'''
        result = subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
