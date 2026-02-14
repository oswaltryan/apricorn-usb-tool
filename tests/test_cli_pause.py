import builtins

from usb_tool import cli


def test_should_pause_when_frozen_no_args(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli.sys, "argv", ["usb.exe"])
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.delenv("USB_TOOL_PAUSE_ON_EXIT", raising=False)
    monkeypatch.delenv("USB_TOOL_NO_PAUSE", raising=False)

    assert cli._should_pause_before_exit() is True


def test_should_not_pause_when_args_present(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli.sys, "argv", ["usb.exe", "--json"])
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.delenv("USB_TOOL_PAUSE_ON_EXIT", raising=False)
    monkeypatch.delenv("USB_TOOL_NO_PAUSE", raising=False)

    assert cli._should_pause_before_exit() is False


def test_force_pause_env_overrides_conditions(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli.sys, "argv", ["usb.exe", "--json"])
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    monkeypatch.setenv("USB_TOOL_PAUSE_ON_EXIT", "1")
    monkeypatch.delenv("USB_TOOL_NO_PAUSE", raising=False)

    assert cli._should_pause_before_exit() is True


def test_pause_helper_invokes_input_when_enabled(monkeypatch):
    calls = {"count": 0}

    def _fake_wait():
        calls["count"] += 1

    monkeypatch.setattr(cli, "_should_pause_before_exit", lambda: True)
    monkeypatch.setattr(cli, "_wait_for_user_acknowledgement", _fake_wait)

    cli._pause_before_exit_if_needed()

    assert calls["count"] == 1


def test_wait_for_user_acknowledgement_uses_input_fallback(monkeypatch):
    calls = {"count": 0}

    def _fake_input(_prompt: str):
        calls["count"] += 1
        return ""

    monkeypatch.setattr(cli, "_SYSTEM", "linux")
    monkeypatch.setattr(builtins, "input", _fake_input)

    cli._wait_for_user_acknowledgement()

    assert calls["count"] == 1
