"""Quartz frontend resources and document assembly.

Every resource in this package is a Python module, not a data file, so a
PyInstaller build that imports ``gui`` picks it up through normal import
analysis. ``Quartz.spec`` lists data files explicitly; adding ``.css``/``.js``
files here would silently leave them out of the packaged application.
See ``docs/CLAUDE_FRONTEND_ARCHITECTURE.md``.
"""
