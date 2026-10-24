"""Project isolation for Quartz's local agent runtimes."""

from __future__ import annotations

import threading
import os
import uuid
from pathlib import Path

from core.atomic_json import atomic_write_json, load_json


class ProjectRegistry:
    """Keep agent commands inside explicitly registered project roots."""

    DEFAULTS = (
        {
            "id": "squad-pilot",
            "name": "Squad Pilot",
            "path": r"C:\SquadPilot",
            "protected": False,
        },
        {"id":"aster-warband", "name":"ASTER · Warband / Universal Modder",
         "path":r"C:\WarbandIsland", "protected":True, "workflow":"warband"},
    )

    def __init__(self, projects=None, storage_path=None):
        self._lock = threading.RLock()
        self.storage_path = Path(storage_path) if storage_path else None
        source = projects if projects is not None else self.DEFAULTS
        self._projects = {}
        for item in source:
            project_id = str(item["id"]).strip()
            path = Path(item["path"]).expanduser().resolve(strict=False)
            self._projects[project_id] = {
                "id": project_id,
                "name": str(item.get("name") or project_id),
                "path": str(path),
                "protected": bool(item.get("protected", False)),
                "workflow": item.get("workflow"),
            }
        self._selected = next(iter(self._projects), None)
        if self.storage_path is not None:
            saved = load_json(self.storage_path, {})
            if isinstance(saved, dict):
                for item in saved.get("projects", []):
                    if not isinstance(item, dict):
                        continue
                    try:
                        path = self._validate_path(item.get("path"), require_exists=False)
                    except (ValueError, FileNotFoundError, PermissionError):
                        continue
                    project_id = str(item.get("id") or "").strip()
                    if project_id and project_id not in self._projects:
                        self._projects[project_id] = {
                            "id": project_id, "name": str(item.get("name") or path.name),
                            "path": str(path), **self._profile(path),
                        }
                selected = saved.get("selected")
                if selected in self._projects:
                    self._selected = selected

    @staticmethod
    def _validate_path(value, *, require_exists=True) -> Path:
        if not value:
            raise ValueError("Project folder is required")
        path = Path(value).expanduser().resolve(strict=require_exists)
        if require_exists and not path.is_dir():
            raise NotADirectoryError(str(path))
        # Only the exact ASTER root gets its protected UM workflow. Subfolders
        # cannot register as generic projects to evade that boundary.
        if os.name == "nt":
            protected = Path(r"C:\WarbandIsland")
            if protected in path.parents:
                raise PermissionError("Register the exact ASTER root for its Universal Modder workflow")
        return path

    @staticmethod
    def _profile(path):
        if os.name=="nt" and path==Path(r"C:\WarbandIsland"):
            return {"protected":True,"workflow":"warband"}
        return {"protected":False,"workflow":None}

    def _save(self) -> None:
        if self.storage_path is not None:
            atomic_write_json(self.storage_path, {
                "selected": self._selected,
                "projects": list(self._projects.values()),
            })

    def add(self, path, name=None) -> dict:
        resolved = self._validate_path(path)
        with self._lock:
            for item in self._projects.values():
                if os.path.normcase(item["path"]) == os.path.normcase(str(resolved)):
                    self._selected = item["id"]
                    self._save()
                    return dict(item)
            project_id = uuid.uuid4().hex[:12]
            item = {"id": project_id, "name": str(name or resolved.name).strip() or resolved.name,
                    "path": str(resolved), **self._profile(resolved)}
            self._projects[project_id] = item
            self._selected = project_id
            self._save()
            return dict(item)

    def list(self) -> list[dict]:
        with self._lock:
            items = []
            for item in self._projects.values():
                path = Path(item["path"])
                value = dict(item)
                value.update({
                    "exists": path.is_dir(),
                    "squad_initialized": (path / ".squad" / "messages.db").is_file(),
                    "selected": item["id"] == self._selected,
                })
                items.append(value)
            return items

    def select(self, project_id: str) -> dict:
        with self._lock:
            project = self._get(project_id)
            if not Path(project["path"]).is_dir():
                raise FileNotFoundError(f"Project folder not found: {project['path']}")
            if self._selected != project["id"]:
                self._selected = project["id"]
                self._save()
            return dict(project)

    def get(self, project_id: str) -> dict:
        with self._lock:
            return dict(self._get(project_id))

    def selected(self) -> dict:
        with self._lock:
            if self._selected is None:
                raise RuntimeError("No agent project is registered")
            return dict(self._get(self._selected))

    def resolve(self, project_id: str | None = None, require_squad=False) -> Path:
        with self._lock:
            project = self._get(project_id or self._selected)
            path = Path(project["path"]).resolve(strict=True)
            if not path.is_dir():
                raise NotADirectoryError(str(path))
            if require_squad and not (path / ".squad" / "messages.db").is_file():
                raise RuntimeError(f"Squad is not initialized for {path}")
            return path

    def _get(self, project_id) -> dict:
        key = str(project_id or "")
        if key not in self._projects:
            raise KeyError(f"Unknown project: {key}")
        return self._projects[key]
