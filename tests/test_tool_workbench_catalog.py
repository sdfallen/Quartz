"""
tests/test_tool_workbench_catalog.py
Unit tests for Tool Workbench catalog registration and capability resolution.
"""

from __future__ import annotations

import unittest

from core.tool_workbench.catalog import BUILTIN_MANIFESTS, ToolCatalog
from core.tool_workbench.contracts import ToolManifest
from core.tool_workbench.errors import ResolutionError


class TestToolWorkbenchCatalog(unittest.TestCase):

    def setUp(self):
        self.catalog = ToolCatalog()

    def test_builtin_manifests_registered(self):
        """Verify built-in manifests (ripgrep, pe_inspector, rea_static) are present."""
        self.assertIn("ripgrep", BUILTIN_MANIFESTS)
        rg = self.catalog.get("ripgrep")
        self.assertIsNotNone(rg)
        self.assertEqual(rg.tool_id, "ripgrep")
        self.assertEqual(rg.version, "14.1.1")
        self.assertEqual(rg.pinned_revision, "14.1.1")
        self.assertTrue(rg.package_digest)
        self.assertIn("binary_string_search", rg.capabilities)

    def test_custom_manifest_registration(self):
        """Register a custom tool manifest dynamically."""
        custom = ToolManifest(
            tool_id="test_tool",
            name="Test Tool",
            version="0.1.0",
            source_url="https://github.com/example/test/releases/v0.1.0/tool.zip",
            pinned_revision="v0.1.0",
            package_digest="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            license="MIT",
            platform=["win32", "windows"],
            capabilities=["test_capability"],
            executable_subpath="bin/test.exe",
            supported_operations={"test": {"options": {}}},
        )
        self.catalog.register(custom)
        fetched = self.catalog.get("test_tool")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.tool_id, "test_tool")

    def test_catalog_query(self):
        """Query catalog with string filter or capability filter."""
        all_tools = self.catalog.catalog()
        self.assertGreaterEqual(len(all_tools), 3)

        # Query by name substring
        rg_query = self.catalog.catalog("ripgrep")
        self.assertEqual(len(rg_query), 1)
        self.assertEqual(rg_query[0]["tool_id"], "ripgrep")

        # Query by capability
        cap_query = self.catalog.catalog({"capability": "pe_header_analysis"})
        self.assertEqual(len(cap_query), 1)
        self.assertEqual(cap_query[0]["tool_id"], "pe_inspector")

        # Query with non-matching filter
        none_query = self.catalog.catalog("nonexistent_tool_xyz")
        self.assertEqual(len(none_query), 0)

    def test_resolve_single_capability(self):
        """Resolve binary string search requirement to ripgrep."""
        res = self.catalog.resolve("binary_string_search")
        self.assertEqual(res["status"], "resolved")
        self.assertTrue(res["resolved"])
        self.assertEqual(res["tool_id"], "ripgrep")
        self.assertEqual(res["pinned_revision"], "14.1.1")
        self.assertEqual(res["package_digest"], "d0f534024c42afd6cb4d38907c25cd2b249b79bbe6cc1dbee8e3e37c2b6e25a1")

    def test_resolve_unsupported_capability(self):
        """Resolve returns unsupported when no candidate exists."""
        res = self.catalog.resolve("quantum_superposition_disassembly")
        self.assertEqual(res["status"], "unsupported")
        self.assertFalse(res["resolved"])
        self.assertIsNone(res["tool_id"])
        self.assertIn("quantum_superposition_disassembly", res["reason"])

    def test_resolve_incompatible_platform(self):
        """Candidate tool incompatible with platform reports limitation."""
        linux_only = ToolManifest(
            tool_id="linux_tool",
            name="Linux Only Tool",
            version="1.0.0",
            source_url="https://github.com/example/linux/releases/tool.zip",
            pinned_revision="1.0.0",
            package_digest="1111111111111111111111111111111111111111111111111111111111111111",
            license="MIT",
            platform=["linux", "darwin"],
            capabilities=["linux_only_capability"],
            executable_subpath="tool",
            supported_operations={"run": {}},
        )
        self.catalog.register(linux_only)
        res = self.catalog.resolve("linux_only_capability")
        self.assertEqual(res["status"], "unsupported")
        self.assertFalse(res["resolved"])
        self.assertIn("incompatible with platform", res["reason"])

    def test_manifest_serialization(self):
        """Manifest to_dict and from_dict roundtrip."""
        rg = self.catalog.get("ripgrep")
        d = rg.to_dict()
        rg_copy = ToolManifest.from_dict(d)
        self.assertEqual(rg.tool_id, rg_copy.tool_id)
        self.assertEqual(rg.package_digest, rg_copy.package_digest)
        self.assertEqual(rg.capabilities, rg_copy.capabilities)


if __name__ == "__main__":
    unittest.main()
