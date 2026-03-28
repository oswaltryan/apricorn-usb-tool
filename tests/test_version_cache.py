import importlib.metadata
import importlib.util
from pathlib import Path

from usb_tool import _version as version_mod

PROJECT_NAME = "apricorn-usb-tool"


def _load_project_version_module():
    script_path = Path.cwd() / "utils" / "project_version.py"
    spec = importlib.util.spec_from_file_location("project_version", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_pyproject(path: Path, version: str, name: str = PROJECT_NAME) -> None:
    path.write_text(
        (f'[project]\nname = "{name}"\nversion = "{version}"\ndescription = "test"\n'),
        encoding="utf-8",
        newline="\n",
    )


def test_get_version_prefers_repo_pyproject_over_installed_metadata(monkeypatch, tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.4.7")
    monkeypatch.delenv("USB_TOOL_VERSION", raising=False)
    monkeypatch.setattr(version_mod, "_module_root_candidates", lambda: iter([tmp_path]))
    monkeypatch.setattr(version_mod.importlib.metadata, "version", lambda _name: "9.8.7")

    resolved = version_mod.get_version()

    assert resolved == "1.4.7"


def test_get_version_falls_back_to_metadata_when_repo_name_mismatches(monkeypatch, tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.4.7", name="not-apricorn-usb-tool")
    monkeypatch.delenv("USB_TOOL_VERSION", raising=False)
    monkeypatch.setattr(version_mod, "_module_root_candidates", lambda: iter([tmp_path]))
    monkeypatch.setattr(version_mod.importlib.metadata, "version", lambda _name: "9.8.7")

    resolved = version_mod.get_version()

    assert resolved == "9.8.7"


def test_get_version_returns_unknown_when_no_source_is_available(monkeypatch):
    monkeypatch.delenv("USB_TOOL_VERSION", raising=False)
    monkeypatch.setattr(version_mod, "_module_root_candidates", lambda: iter(()))

    def _missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(version_mod.importlib.metadata, "version", _missing)

    resolved = version_mod.get_version()

    assert resolved == "Unknown"


def test_read_version_requires_expected_project_name(tmp_path):
    project_mod = _load_project_version_module()
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.4.0", name="other-project")

    try:
        project_mod.read_version(pyproject)
    except RuntimeError as exc:
        assert PROJECT_NAME in str(exc)
    else:
        raise AssertionError("Expected read_version() to reject the wrong project name")


def test_bump_if_needed_updates_pyproject_when_head_matches(monkeypatch, tmp_path):
    project_mod = _load_project_version_module()
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.4.0")

    monkeypatch.setattr(project_mod, "PYPROJECT", pyproject)
    monkeypatch.setattr(
        project_mod,
        "_read_head_file",
        lambda path: '[project]\nname = "apricorn-usb-tool"\nversion = "1.4.0"\n',
    )

    assert project_mod.bump_if_needed() == 0
    assert project_mod.read_version(pyproject) == "1.4.1"


def test_bump_if_needed_preserves_manual_version_change(monkeypatch, tmp_path):
    project_mod = _load_project_version_module()
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject, "1.5.0")

    monkeypatch.setattr(project_mod, "PYPROJECT", pyproject)
    monkeypatch.setattr(
        project_mod,
        "_read_head_file",
        lambda path: '[project]\nname = "apricorn-usb-tool"\nversion = "1.4.0"\n',
    )

    assert project_mod.bump_if_needed() == 0
    assert project_mod.read_version(pyproject) == "1.5.0"
