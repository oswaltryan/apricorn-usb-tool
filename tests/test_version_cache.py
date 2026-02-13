from pathlib import Path
from uuid import uuid4

from usb_tool import _version as version_mod


def _repo_temp_cache_file() -> Path:
    return Path.cwd() / f".tmp_cached_version_{uuid4().hex}.txt"


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
