import builtins

from usb_tool import cli


def test_should_pause_when_frozen_no_args_and_standalone_console(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli.sys, "argv", ["usb.exe"])
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli, "_is_standalone_windows_console_launch", lambda: True)
    monkeypatch.delenv("USB_TOOL_PAUSE_ON_EXIT", raising=False)

    assert cli._should_pause_before_exit() is True


def test_should_not_pause_when_terminal_attached(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli.sys, "argv", ["usb.exe"])
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli, "_is_standalone_windows_console_launch", lambda: False)
    monkeypatch.delenv("USB_TOOL_PAUSE_ON_EXIT", raising=False)

    assert cli._should_pause_before_exit() is False


def test_should_not_pause_when_args_present(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli.sys, "argv", ["usb.exe", "--json"])
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli, "_is_standalone_windows_console_launch", lambda: True)
    monkeypatch.delenv("USB_TOOL_PAUSE_ON_EXIT", raising=False)

    assert cli._should_pause_before_exit() is False


def test_force_pause_env_overrides_conditions(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli.sys, "argv", ["usb.exe", "--json"])
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    monkeypatch.setattr(cli, "_is_standalone_windows_console_launch", lambda: False)
    monkeypatch.setenv("USB_TOOL_PAUSE_ON_EXIT", "1")

    assert cli._should_pause_before_exit() is True


def test_standalone_console_detection_accepts_explorer_parent(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli, "_get_parent_process_chain_windows", lambda: ["explorer.exe"])

    assert cli._is_standalone_windows_console_launch() is True


def test_standalone_console_detection_rejects_terminal_parent(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli, "_get_parent_process_chain_windows", lambda: ["powershell.exe"])

    assert cli._is_standalone_windows_console_launch() is False


def test_standalone_console_detection_handles_missing_parent(monkeypatch):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(cli, "_get_parent_process_chain_windows", lambda: [])

    assert cli._is_standalone_windows_console_launch() is False


def test_standalone_console_detection_accepts_explorer_in_ancestor_chain(
    monkeypatch,
):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(
        cli,
        "_get_parent_process_chain_windows",
        lambda: ["openconsole.exe", "explorer.exe"],
    )

    assert cli._is_standalone_windows_console_launch() is True


def test_standalone_console_detection_rejects_terminal_before_explorer(
    monkeypatch,
):
    monkeypatch.setattr(cli, "_SYSTEM", "windows")
    monkeypatch.setattr(
        cli,
        "_get_parent_process_chain_windows",
        lambda: ["conhost.exe", "powershell.exe", "explorer.exe"],
    )

    assert cli._is_standalone_windows_console_launch() is False


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
