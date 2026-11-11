"""Execute the actual diagnostics fragment; no screenshot/GUI acceptance implied."""
import json
import subprocess
import unittest
from unittest.mock import patch

from core.diagnostics_intent import diagnostics_intent
from ui.js_diagnostics import JAVASCRIPT


class InvestigationFrontendTests(unittest.TestCase):
    def test_cached_evidence_is_not_labelled_disabled_or_new_execution(self):
        script="const assert=require('node:assert/strict'); const document={getElementById:()=>null,addEventListener:()=>{}};\n"+JAVASCRIPT.split("  safeBtn.addEventListener(",1)[0]+"""
const view=buildSelfDiagnosticsView({id:'j',state:'completed',phase:'done',progress:100,
 verdict:'PASS',finished_at:1,rea_used:false,checks:[{id:'rea',status:'PASS'}],
 investigation:{knowledge_reused:true,evidence_count:2,findings_count:3,raw_secret:'never render this'},
 investigation_knowledge_saved:true});
assert.equal(view.reaUsed,false);assert.match(view.reaTagText,/Önceki kanıt/);
const data=JSON.parse(view.technicalSummaryText);
assert.equal(data.investigation.evidence_count,2);assert.equal(data.investigation.knowledge_reused,true);
assert.equal(data.investigation.instruction_authority,false);
assert(!view.technicalSummaryText.includes('never render this'));
"""
        result=subprocess.run(['node','-'],input=script,text=True,capture_output=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_research_intent_keeps_quotation_question_and_no_tool_boundaries(self):
        for message in ['Bir uygulamayı REA ile araştır','Seçtiğim oyunun motorunu analiz et']:
            self.assertEqual(diagnostics_intent(message),'artifact')
        for message in ['Seçtiğim oyunun motorunu analiz et?', '"Bir uygulamayı REA ile araştır" ne yapar?',
                        'Araç kullanma, seçtiğim oyunun motorunu analiz et']:
            self.assertIsNone(diagnostics_intent(message))

    def test_same_chat_question_reaches_picker_without_arbitrary_target_path(self):
        import gui
        api=gui.Api()
        with patch.object(api,'diagnostics_select_application',return_value={'status':'ok','data':None}) as picker, \
             patch.object(api,'natural_start') as natural:
            response=api.coordination_route('Bir uygulamayı REA ile araştır','c','p',{})
        self.assertEqual(response['status'],'ok')
        picker.assert_called_once_with(question='Bir uygulamayı REA ile araştır')
        natural.assert_not_called()


if __name__=='__main__':unittest.main()
