"""Production routing and honest connection status; no real account access."""
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import gui
from tests import test_notion_runtime as fixture
from core.notion_cli import NotionError


class NotionConnectionTests(unittest.TestCase):
    setUp = fixture.NotionRuntimeTests.setUp
    reply = fixture.NotionRuntimeTests.reply

    def test_configuration_alone_is_not_connected(self):
        with patch('core.notion_runtime.resolve_ntn', return_value='ntn.exe'):
            self.assertFalse(self.runtime.probe()['ready'])
            self.runtime.connection_status()
            self.runtime._connection_worker.join(1)
            status = self.runtime.connection_status()
        self.assertTrue(status['ready'])
        self.assertTrue(status['auth_verified'])
        self.assertEqual(status['agent_name'], 'Test ajanı')

    def test_failed_authentication_never_reports_ready(self):
        self.client.agents.side_effect = NotionError('Giriş gerekli', code='unauthorized')
        with patch('core.notion_runtime.resolve_ntn', return_value='ntn.exe'):
            self.runtime.connection_status()
            self.runtime._connection_worker.join(1)
            result = self.runtime.connection_status()
        self.assertFalse(result['ready'])
        self.assertEqual(result['authentication'], 'unverified')

    def test_old_scope_worker_cannot_publish_new_agent_ready(self):
        import threading
        from core.atomic_json import atomic_write_json
        entered, release = threading.Event(), threading.Event()
        def agents():
            entered.set()
            release.wait(2)
            return [{'id': fixture.AGENT, 'name': 'Old'}]
        self.client.agents.side_effect = agents
        with patch('core.notion_runtime.resolve_ntn', return_value='ntn.exe'):
            self.runtime.connection_status()
            self.assertTrue(entered.wait(1))
            atomic_write_json(self.runtime.home / 'connection.json', {'workspace_id':fixture.WORKSPACE,'agent_id':fixture.OTHER})
            self.assertFalse(self.runtime.connection_status()['ready'])
            release.set()
            self.runtime._connection_worker.join(1)
            self.assertIsNone(self.runtime._connection_cache)


class NotionGuiRoutingTests(unittest.TestCase):
    def test_notion_task_cannot_start_or_instruct_local_desktop(self):
        api = gui.Api()
        api._natural = MagicMock()
        with patch.object(api, 'natural_start') as start, patch('gui.ipc_send') as ipc:
            for text, agent in (("Steam'i aç ve incele", 'notion'), ('@notion Quartz uygulamasını incele', 'codex')):
                result = api.coordination_route(text, 'c', 'p', {}, 'full', agent)
                self.assertEqual(result, {'status':'ok','data':{'handled':False,'intent':'conversation'}})
            start.assert_not_called()
            api._natural.instruct.assert_not_called()
            ipc.assert_not_called()

    def test_onboarding_combines_real_notion_state_without_mutating_cached_providers(self):
        api = gui.Api()
        original = {'providers': {'codex': {'ready':False}, 'gemini': {'ready':False}}, 'needs_setup':True}
        api._onboarding = MagicMock()
        api._onboarding.status.return_value = original
        with patch('gui.ipc_send', return_value={'status':'ok','data':{'ready':True,'agent_name':'Test'}}) as ipc:
            result = api.onboarding_status()
        ipc.assert_called_once_with('notion_status', {'force':False})
        self.assertTrue(result['data']['providers']['notion']['ready'])
        self.assertFalse(result['data']['needs_setup'])
        self.assertNotIn('notion', original['providers'])

    def test_notion_checking_is_polled_even_with_setup_modal_closed(self):
        source=gui._HTML
        function=source[source.index('  function renderCliStatus(data)'):source.index('  async function refreshCliStatus(')]
        harness=r'''
const assert=require('node:assert/strict');let cliState=null,cliPollTimer=null;const timers=[];
function node(){return {textContent:'',dataset:{},attrs:{},children:[],disabled:false,
 classList:{contains:()=>false},setAttribute(k,v){this.attrs[k]=v},append(...c){this.children.push(...c)},replaceChildren(){this.children=[]}}}
const elements=new Map();function el(id){if(!elements.has(id))elements.set(id,node());return elements.get(id)}
const notion=node();notion.dataset.agent='notion';
const document={getElementById:el,createElement:node,querySelectorAll:()=>[notion]};
function clearTimeout(){}function setTimeout(fn,ms){timers.push(ms);return timers.length}function refreshCliStatus(){}
'''
        checks=r'''
renderCliStatus({providers:{notion:{installed:true,configured:true,checking:true,ready:false}}});
assert.equal(notion.disabled,true);assert.deepEqual(timers,[1500]);
renderCliStatus({providers:{notion:{ready:true,agent_name:'Test Agent'}}});
assert.equal(notion.disabled,false);assert.equal(notion.attrs['aria-disabled'],'false');
assert.equal(el('notionAgentName').textContent,'Test Agent');
'''
        result=subprocess.run(['node','-e',harness+function+checks],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
