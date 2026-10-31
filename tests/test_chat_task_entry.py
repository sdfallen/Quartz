"""Main composer is the sole normal entry: routing never grants UI authority."""
import re
import subprocess
import unittest
from unittest.mock import Mock, patch

import gui
from core.desktop_task_ui import desktop_intent
from core.message_intent import message_intent


class ChatTaskEntryTests(unittest.TestCase):
    REQUESTS = (
        'Ekrana bak', 'Ekranda ne görüyorsun?', 'Ayarlar ekranına gir',
        'Pekala hadi bi deneme yapalım. Codex Masaüstünü incelermisin?',
        'Ekrana bakabilirmisin?', 'Pencereyi açarmısınız?',
        'Test uygulamasına geç', 'Notepad açar mısın?',
        'Açık pencereye bakabilir misiniz?', 'Tarayıcıyı kontrol eder misin?',
        'Ekran görüntüsü al', 'Şu penceredeki düğmeye bas',
        'Click the button in the test application', 'Inspect the active window',
        'Take a screenshot of the application',
        "Codex, Quartz'ın ayarlar ekranını aç, incele ve sorunu düzelt. Gemini, logları kontrol et.",
    )

    def test_desktop_requests_reach_tools_from_the_same_chat_without_a_draft(self):
        for text in self.REQUESTS:
            with self.subTest(text=text):
                self.assertEqual(message_intent(text),'task')
                self.assertEqual(desktop_intent(text),'task')
                api=gui.Api()
                with patch.object(api,'natural_start',return_value={'status':'ok','data':{'handled':True,'natural_started':True}}) as start, \
                     patch.object(api,'coordination_prepare',side_effect=AssertionError('Separate task form used')):
                    result=api.coordination_route(text,'c','p',{},'project')
                self.assertTrue(result['data']['natural_started'])
                start.assert_called_once_with(text,'c','p',{},'project')
                self.assertIsNone(api._desktop_agents)

    def test_discussion_and_quoted_commands_never_start_a_desktop_task(self):
        for text in ('Merhaba dostum', 'Quartz hakkında ne düşünüyorsun?',
                'Ekran görüntüsü nasıl alınır?', 'How do I click a button?',
                '"Notepad aç" ne demek?', '```Ekrana bak``` komutunu açıkla',
                'Araç kullanma, ekrana bak', 'Sadece sohbet edelim; uygulamayı aç'):
            with self.subTest(text=text):
                api=gui.Api()
                with patch.object(api,'natural_start') as start, patch('gui.ipc_send') as ipc:
                    result=api.coordination_route(text,'c','p',{})
                start.assert_not_called();ipc.assert_not_called()
                self.assertEqual(result['data']['intent'],'conversation')

    def test_source_task_keeps_existing_checkpointed_file_workflow(self):
        api=gui.Api()
        with patch.object(api,'natural_start') as start, patch('gui.ipc_send',return_value={'status':'ok','data':{'projects':[{'id':'p'}]}}):
            result=api.coordination_route('Pencere çizim sınıfının kodunu düzelt','c','p',{})
        start.assert_not_called()
        self.assertFalse(result['data']['handled']);self.assertEqual(result['data']['intent'],'task')

    def test_same_chat_followup_instructs_existing_task_and_stop_revokes_it(self):
        api=gui.Api();task=Mock()
        task.status.return_value={'active':True,'job':{'conversation_id':'c'}}
        api._natural=task
        with patch('gui.ipc_send',return_value={'status':'ok'}):
            result=api.coordination_route('Şu pencereye bak','c','p',{})
            self.assertTrue(result['data']['instructed'])
            task.instruct.assert_called_once_with('Şu pencereye bak','c')
            api.coordination_route('Durdur','c','p',{})
        task.stop.assert_called_once()

    def test_desktop_start_failure_is_visible_not_downgraded_to_toolless_chat(self):
        api=gui.Api()
        with patch.object(api,'natural_start',return_value={'status':'error','data':'specific startup failure'}):
            result=api.coordination_route('Ekrana bak','c','p',{})
        self.assertEqual(result,{'status':'error','data':'specific startup failure'})

    def test_main_composer_dispatches_once_and_does_not_confirm_a_fake_start_mode(self):
        function=re.search(r'async function sendAgentMessage\(\)[\s\S]*?\n  }\n',gui._HTML).group(0)
        code=r'''
const assert=require('assert');let routed=0,read=0;global.coordinationRouting=false;
global.inputEl={value:'Ekrana bak'};global.currentConvId='c';global.mainProjectSelect={value:'p'};
global.mainAgentSelect={value:'codex'};
global.codexModelSelect=global.agyModelSelect={value:'model'};
global.codexEffortSelect=global.agyEffortSelect={value:'low'};
global.document={getElementById:()=>({value:'project'})};
global.window={confirm:()=>{throw Error('Separate start confirmation')},pywebview:{api:{
 coordination_route:async(...args)=>{routed++;assert.equal(args[0],'Ekrana bak');return {status:'ok',data:{handled:true,natural_started:true}}},
 chat_send:()=>{throw Error('Duplicate toolless dispatch')}}}};
global.refreshDesktopTaskState=async()=>{read++};global.pollNaturalTask=async()=>{read++};
global.appendMsg=()=>{throw Error('Unexpected extra start form')};
''' + function + r'''
sendAgentMessage().then(()=>{assert.equal(routed,1);assert.equal(read,2);assert.equal(inputEl.value,'');assert.equal(coordinationRouting,false)})
.catch(e=>{console.error(e);process.exitCode=1});
'''
        run=subprocess.run(['node','-e',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__':unittest.main()
