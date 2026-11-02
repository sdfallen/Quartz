"""Real local child execution through the same JSON/evidence host boundary."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from core.investigation.gateway import InvestigationToolGateway
from core.investigation.planning import InvestigationPolicy
from core.investigation.session import InvestigationSession
from core.tool_workbench import ToolManifest, ToolWorkbench


class WorkbenchHostBoundary(unittest.TestCase):
    def test_real_child_json_receipt_is_captured_replayed_and_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'input.txt'
            target.write_text('QUARTZ_INDEPENDENT_MATCH', encoding='utf-8')
            workspace = root / 'work'
            workspace.mkdir()
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as z:
                z.writestr('scan.py', 'import pathlib,sys\nprint(pathlib.Path(sys.argv[-1]).read_text())\n')
            archive = data.getvalue()
            manifest = ToolManifest('local-review','Local review','1',
                'https://github.com/quartz-tests/fixture/archive.zip','1',
                hashlib.sha256(archive).hexdigest(),'test',['any'],['text_search'],
                'scan.py',{'scan':{'options':{}}})
            workbench = ToolWorkbench(managed_dir=root/'managed',workspace_dir=workspace)
            workbench.catalog_service.register(manifest)
            response = io.BytesIO(archive)
            response.geturl = lambda: manifest.source_url
            event = threading.Event()
            session = InvestigationSession(target,root=root/'memory',event=event,
                deadline=time.monotonic()+25,tool_identity={'test':'actual-child'})
            gateway = InvestigationToolGateway(session,workbench,workspace=workspace,
                policy=InvestigationPolicy(effects=frozenset({'read_target','write_workspace','execute_tool'})),
                tool_specs={manifest.tool_id:{'source_url':manifest.source_url,
                    'pinned_revision':manifest.pinned_revision,'package_digest':manifest.package_digest,
                    'operations':['scan'],'effects':['read_target','write_workspace','execute_tool']}})
            try:
                with patch('core.tool_workbench.acquisition.urllib.request.build_opener') as opener:
                    opener.return_value.open.return_value = response
                    workbench.acquire(manifest)
                request={'investigation_id':session.evidence.id,'step_id':'actual-scan',
                    'tool_id':manifest.tool_id,'operation':'scan','target':session.target.as_dict(),
                    'workspace':str(workspace),'options':{}}
                receipt=gateway.execute(request,event)
                self.assertEqual(receipt['status'],'completed')
                self.assertEqual(receipt['request_id'],session.evidence.id+'.actual-scan')
                self.assertEqual(receipt['cleanup_receipt']['status'],'confirmed')
                self.assertGreater(receipt['process_identity']['pid'],0)
                self.assertTrue(receipt['artifacts'])
                outputs=[(workspace/a['path']).read_bytes() for a in receipt['artifacts']]
                self.assertTrue(any(b'QUARTZ_INDEPENDENT_MATCH' in b for b in outputs))
                session.evidence.finalize("completed")
                self.assertTrue(all(session.evidence.verify_record(root/"memory", r, event, session.deadline) for r in session.evidence.records.values()))
                again=gateway.execute(request,event)
                self.assertTrue(again['replayed_receipt'])
                self.assertEqual(again['process_identity'],receipt['process_identity'])
                self.assertEqual(len(list(workspace.glob('run_*'))),1)
                json.dumps(receipt,allow_nan=False)
            finally:
                self.assertEqual(gateway.close()['status'],'confirmed')
                self.assertEqual(workbench.close()['status'],'confirmed')
                session.close()

    def test_all_requirements_and_empty_catalog_are_respected(self):
        from core.tool_workbench.catalog import ToolCatalog
        self.assertEqual(ToolCatalog({}).catalog(),[])
        catalog=ToolCatalog()
        self.assertFalse(catalog.resolve([{'capability_id':'text_search'},
            {'capability_id':'nonexistent-disassembly'}])['resolved'])
        self.assertFalse(catalog.resolve({'capability_id':'text_search',
            'target_format':'unsupported-private-engine-format'})['resolved'])

    def test_unregistered_manifest_and_default_close_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            workbench=ToolWorkbench(managed_dir=Path(directory)/'managed',workspace_dir=Path(directory)/'work')
            self.assertEqual(workbench.close()['status'],'confirmed')
            self.assertEqual(workbench.close()['status'],'confirmed')
            with self.assertRaises(Exception): workbench.acquire('ripgrep')

    def test_json_resource_types_cannot_be_laundered(self):
        from core.tool_workbench.contracts import ToolRequest
        base={'investigation_id':'test','step_id':'step','tool_id':'ripgrep','operation':'search'}
        for value in (True, '1024', 1.5, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ToolRequest.from_dict(dict(base,max_output_bytes=value))
        for value in (True, '10', float('nan'),float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ToolRequest.from_dict(dict(base,deadline_monotonic=value))

    def test_official_source_defaults_do_not_allow_alternate_ports(self):
        from core.tool_workbench.acquisition import _source_allowed
        self.assertTrue(_source_allowed('https://github.com/owner/repo', ['https://github.com/']))
        self.assertFalse(_source_allowed('https://github.com:8443/owner/repo', ['https://github.com/']))
        self.assertFalse(_source_allowed('https://github.com.evil.invalid/repo', ['https://github.com/']))

if __name__=='__main__':unittest.main()
