from pathlib import Path
from uuid import uuid4

import importlib.metadata
import importlib.util

from usb_tool import _version as version_mod


def _repo_temp_cache_file() -> Path:
    return Path.cwd() / f".tmp_cached_version_{uuid4().hex}.txt"


def _load_sync_version_module():
    script_path = Path.cwd() / "scripts" / "sync_cached_version.py"
    spec = importlib.util.spec_from_file_location("sync_cached_version", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_cached_version_uses_trailing_newline(monkeypatch):
    cache_file = _repo_temp_cache_file()
    try:
        monkeypatch.setattr(version_mod, "CACHE_FILE", cache_file)

        version_mod._write_cached_version("1.2.3")

        assert cache_file.read_text(encoding="utf-8") == "1.2.3\n"
    finally:
        cache_file.unlink(missing_ok=True)


def test_write_cached_version_ignores_blank_values(monkeypatch):
    cache_file = _repo_temp_cache_file()
    try:
        monkeypatch.setattr(version_mod, "CACHE_FILE", cache_file)

        version_mod._write_cached_version("   ")

        assert not cache_file.exists()
    finally:
        cache_file.unlink(missing_ok=True)


def test_get_version_prefers_cached_version_over_installed_metadata(monkeypatch):
    cache_file = _repo_temp_cache_file()
    try:
        cache_file.write_text("1.4.7\n", encoding="utf-8", newline="\n")
        monkeypatch.setattr(version_mod, "CACHE_FILE", cache_file)
        monkeypatch.delenv("USB_TOOL_VERSION", raising=False)
        monkeypatch.setattr(
            version_mod.importlib.metadata, "version", lambda _name: "9.8.7"
        )

        resolved = version_mod.get_version()

        assert resolved == "1.4.7"
        assert cache_file.read_text(encoding="utf-8") == "1.4.7\n"
    finally:
        cache_file.unlink(missing_ok=True)


def test_get_version_falls_back_to_cached_version_when_metadata_missing(monkeypatch):
    cache_file = _repo_temp_cache_file()
    try:
        cache_file.write_text("1.4.0\n", encoding="utf-8", newline="\n")
        monkeypatch.setattr(version_mod, "CACHE_FILE", cache_file)
        monkeypatch.delenv("USB_TOOL_VERSION", raising=False)

        def _missing(_name: str) -> str:
            raise importlib.metadata.PackageNotFoundError

        monkeypatch.setattr(version_mod.importlib.metadata, "version", _missing)

        resolved = version_mod.get_version()

        assert resolved == "1.4.0"
    finally:
        cache_file.unlink(missing_ok=True)


def test_sync_cached_version_bumps_patch_when_head_base_matches(monkeypatch):
    sync_mod = _load_sync_version_module()

    monkeypatch.setattr(
        sync_mod, "_read_pyproject_version", lambda path=sync_mod.PYPROJECT: "1.4.0"
    )
    monkeypatch.setattr(
        sync_mod,
        "_read_head_file",
        lambda path: {
            "pyproject.toml": '[project]\nversion = "1.4.0"\n',
            "src/usb_tool/_cached_version.txt": "1.4.7",
        }.get(path),
    )

    assert sync_mod._resolve_target_version() == "1.4.8"


def test_sync_cached_version_resets_when_pyproject_base_changes(monkeypatch):
    sync_mod = _load_sync_version_module()

    monkeypatch.setattr(
        sync_mod, "_read_pyproject_version", lambda path=sync_mod.PYPROJECT: "1.5.0"
    )
    monkeypatch.setattr(
        sync_mod,
        "_read_head_file",
        lambda path: {
            "pyproject.toml": '[project]\nversion = "1.4.0"\n',
            "src/usb_tool/_cached_version.txt": "1.4.7",
        }.get(path),
    )

    assert sync_mod._resolve_target_version() == "1.5.0"
