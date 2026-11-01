"""Frontend boundary contracts: ui/ assembly, packaging paths, offline, API surface."""
import ast
import base64
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gui
from ui import document
from ui.app_js import APPLICATION_JS, SCRIPT_DOCUMENT, SCRIPT_PARTS
from ui.shell import SHELL_MARKUP
from ui.styles import BASE_CSS
from ui.theme import MODERN_CSS

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_BLOCK = re.compile(r"<script>(.*?)</script>", re.S)

# pywebview js_api surface at baseline 59e3533. JavaScript calls these names
# through window.pywebview.api; additions are fine, removals/renames are not.
BASELINE_API = frozenset("""
agent_center_cancel agent_center_dispatch agent_center_status cancel_request
cancel_task chat_cancel chat_continue chat_delete chat_delete_project chat_models
chat_new chat_poll chat_prepare_resume chat_response_detail chat_select chat_send
chat_set_agent chat_set_model chat_set_project chat_status cleanup_before_exit
clear_history close configure_api coordination_approve coordination_cancel_plan
coordination_pick_app coordination_pick_log coordination_prepare coordination_route
coordination_status coordination_stop copy_mobile_token desktop_operator_start
desktop_operator_status desktop_operator_stop desktop_operator_windows
desktop_task_status desktop_task_stop diagnostics_apply_repair diagnostics_cancel
diagnostics_discard_repair diagnostics_learned_applications diagnostics_prepare_repair
diagnostics_select_application diagnostics_start diagnostics_status get_stats health
minimize mobile_access natural_approve natural_deny natural_start natural_status
onboarding_begin onboarding_refresh onboarding_status ping project_pick_add
project_select provider_probe push_to_talk quick_action send_chat set_compact
set_safe_mode set_screen_advisor set_tool_source set_tts_enabled tasks
toggle_wake_word tool_permissions ui_events voice_status writer_recovery_acknowledge
writer_recovery_inspect
""".split())


def _fake_assets(root: Path, png: bytes | None = b"\x89PNG-test") -> Path:
    assets = root / "assets"
    (assets / "branding").mkdir(parents=True)
    (assets / "workspace.css").write_text(".fake-workspace{color:red}", encoding="utf-8")
    if png is not None:
        (assets / "branding" / "quartz-q-48.png").write_bytes(png)
    return assets


class DocumentAssemblyTests(unittest.TestCase):
    def test_document_order_is_head_base_theme_workspace_modern_then_body(self):
        workspace = (ROOT / "assets" / "workspace.css").read_text(encoding="utf-8")
        prefix = (document.DOCUMENT_HEAD + "<style>\n" + BASE_CSS + "</style>"
                  + "\n<style>" + workspace + "</style>"
                  + '<style id="quartz-modern-theme">' + MODERN_CSS + "</style></head>")
        self.assertTrue(gui._HTML.startswith(prefix))
        self.assertTrue(gui._HTML.rstrip().endswith("</html>"))
        self.assertEqual(gui._HTML.count(BASE_CSS), 1)

    def test_body_is_passed_through_unchanged_apart_from_brand_mark(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = _fake_assets(Path(directory), png=None)
            built = document.build_document(gui._HTML_BODY, assets)
        self.assertTrue(built.endswith(gui._HTML_BODY.replace(
            "</head>", "<style>.fake-workspace{color:red}</style>"
            '<style id="quartz-modern-theme">' + MODERN_CSS + "</style></head>", 1)))

    def test_frozen_bundle_root_is_used_for_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = _fake_assets(root)
            with patch.object(sys, "_MEIPASS", str(root), create=True):
                self.assertEqual(document.asset_root(), assets)
                built = document.build_document("\n</head>\n<body>" + document.BRAND_PLACEHOLDER + "</body>")
        self.assertIn(".fake-workspace{color:red}", built)
        self.assertIn("data:image/png;base64," + base64.b64encode(b"\x89PNG-test").decode("ascii"), built)
        self.assertNotIn(document.BRAND_PLACEHOLDER, built)

    def test_source_checkout_root_is_repository_assets(self):
        if hasattr(sys, "_MEIPASS"):
            self.skipTest("running inside a frozen bundle")
        self.assertEqual(document.asset_root(), ROOT / "assets")
        self.assertEqual(gui._ASSET_ROOT, ROOT / "assets")
        self.assertEqual(gui._BRAND_MARK, ROOT / "assets" / "branding" / "quartz-q-48.png")

    def test_missing_brand_mark_keeps_text_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = _fake_assets(Path(directory), png=None)
            built = document.build_document("\n</head>" + document.BRAND_PLACEHOLDER, assets)
        self.assertIn(document.BRAND_PLACEHOLDER, built)
        self.assertNotIn('class="brand-icon"', built)

    def test_missing_workspace_css_still_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                document.build_document("\n</head>", Path(directory) / "assets")

    def test_shipped_document_keeps_brand_and_turkish_shell(self):
        self.assertIn('class="brand-icon"', gui._HTML)
        self.assertIn('<html lang="tr">', gui._HTML)
        self.assertIn('<meta charset="UTF-8">', gui._HTML)


class PackagingContractTests(unittest.TestCase):
    def test_ui_package_contains_only_python_modules(self):
        # Quartz.spec bundles data files from an explicit allow-list only.
        files = [p for p in (ROOT / "ui").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        self.assertTrue(files)
        self.assertEqual([p.name for p in files if p.suffix != ".py"], [])

    def test_ui_modules_are_reachable_by_static_import_analysis(self):
        def imported(path):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            return {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
        self.assertIn("ui.document", imported(ROOT / "gui.py"))
        self.assertIn("ui.app_js", imported(ROOT / "gui.py"))
        self.assertIn("ui.styles", imported(ROOT / "ui" / "document.py"))
        self.assertEqual({"ui.js_setup", "ui.js_messages", "ui.js_chat", "ui.js_desktop",
                          "ui.js_diagnostics", "ui.js_advanced", "ui.js_lifecycle"},
                         imported(ROOT / "ui" / "app_js.py"))

    def test_document_loads_no_remote_resources(self):
        html = gui._HTML
        self.assertNotRegex(html, r"<link\b")
        self.assertNotRegex(html, r"@import")
        self.assertNotRegex(html, r"<script\s+[^>]*src=")
        self.assertNotRegex(html, r"""\bsrc=["']?(https?:)?//""")
        self.assertNotRegex(html, r"""url\(\s*["']?(https?:)?//""")


class ScriptAndApiContractTests(unittest.TestCase):
    def test_javascript_checker_reads_shipped_composition_and_rejects_empty_fragments(self):
        from scripts.check_gui_javascript import shipped_application_script
        self.assertEqual(shipped_application_script(), APPLICATION_JS)
        with patch("ui.app_js.SCRIPT_PARTS", (SCRIPT_PARTS[0], "")):
            with self.assertRaisesRegex(ValueError, "fragment missing or empty"):
                shipped_application_script()
        with patch("ui.app_js.SCRIPT_DOCUMENT", "<script></script>"):
            with self.assertRaises(ValueError):
                shipped_application_script()
        with patch("ui.app_js.APPLICATION_JS", APPLICATION_JS + "\n"):
            with self.assertRaisesRegex(ValueError, "composition differs"):
                shipped_application_script()

    def test_application_javascript_is_composed_in_one_shared_script_scope(self):
        source = (ROOT / "gui.py").read_text(encoding="utf-8")
        shipped = SCRIPT_BLOCK.findall(gui._HTML)
        self.assertEqual(shipped, [APPLICATION_JS])
        self.assertEqual(SCRIPT_BLOCK.findall(SCRIPT_DOCUMENT), shipped)
        self.assertEqual(SCRIPT_BLOCK.findall(source), [])
        self.assertEqual(len(SCRIPT_PARTS), 7)
        self.assertTrue(all(part.strip() for part in SCRIPT_PARTS))
        self.assertEqual(APPLICATION_JS, "".join(SCRIPT_PARTS))

    def test_base_theme_is_not_duplicated_in_gui_source(self):
        source = (ROOT / "gui.py").read_text(encoding="utf-8")
        self.assertNotIn("--bg-void:", source)
        self.assertIn("--bg-void:", BASE_CSS)

    def test_pywebview_api_surface_is_preserved(self):
        current = {name for name in dir(gui.Api)
                   if not name.startswith("_") and callable(getattr(gui.Api, name))}
        self.assertEqual(sorted(BASELINE_API - current), [])


class ShellMarkupBoundaryTests(unittest.TestCase):
    """Shell markup and ordered JS fragments are assembled outside the bridge."""

    def test_body_is_shell_markup_followed_by_the_composed_application_script(self):
        self.assertTrue(gui._HTML_BODY.startswith(SHELL_MARKUP))
        rest = gui._HTML_BODY[len(SHELL_MARKUP):]
        self.assertTrue(rest.startswith("<script>"))
        scripts = SCRIPT_BLOCK.findall(SCRIPT_DOCUMENT)
        # Exactly one application script, and the syntax check sees all of it;
        # an empty match list must never be mistaken for a passing check.
        self.assertEqual(len(scripts), 1)
        self.assertGreater(len(scripts[0].strip()), 1000)
        self.assertEqual(SCRIPT_BLOCK.findall(rest), scripts)
        self.assertEqual(rest, SCRIPT_DOCUMENT)
        self.assertTrue(rest.rstrip().endswith("</html>"))

    def test_shell_markup_is_presentation_only(self):
        self.assertTrue(SHELL_MARKUP.startswith("\n</head>\n<body>\n"))
        self.assertNotRegex(SHELL_MARKUP, r"<script\b")
        self.assertNotIn("pywebview.api", SHELL_MARKUP)
        self.assertNotRegex(SHELL_MARKUP, r"\son[a-z]+\s*=")  # no inline handlers
        self.assertNotIn("notion", SHELL_MARKUP.lower())  # suspended Notion controls stay out
        tree = ast.parse((ROOT / "ui" / "shell.py").read_text(encoding="utf-8"))
        self.assertEqual([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))], [])

    def test_shell_keeps_stop_permission_model_and_chat_controls(self):
        ids = set(re.findall(r'\bid="([^"]+)"', SHELL_MARKUP))
        for required in ("chat", "msgInput", "btnSend", "btnCancel", "btnHudStopTask",
                         "btnDesktopTaskStop", "btnDesktopStop", "screenControlHud",
                         "mainPermissionLevel", "codexModelSelect", "agyModelSelect"):
            self.assertIn(required, ids)
        self.assertEqual(len(re.findall(r'\bid="', SHELL_MARKUP)), len(ids), "duplicate ids")
        self.assertIn(document.BRAND_PLACEHOLDER, SHELL_MARKUP)

    def test_every_id_the_script_looks_up_by_literal_exists_in_the_shell(self):
        script = gui._HTML_BODY[len(SHELL_MARKUP):]
        wanted = set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", script))
        self.assertTrue(wanted)
        built_ids = set(re.findall(r'\bid="([^"]+)"', gui._HTML))
        created = set(re.findall(r"\.id\s*=\s*'([A-Za-z0-9_-]+)'", script))
        self.assertEqual(sorted(wanted - built_ids - created), [])

    def test_gui_imports_shell_statically_for_pyinstaller(self):
        tree = ast.parse((ROOT / "gui.py").read_text(encoding="utf-8"))
        modules = {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
        self.assertIn("ui.shell", modules)
        self.assertIn("ui.app_js", modules)


if __name__ == "__main__":
    unittest.main()
