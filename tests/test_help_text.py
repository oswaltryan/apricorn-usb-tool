from usb_tool import help_text


def test_linux_help_displays_resolved_version_and_linux_targets(capfd, monkeypatch):
    monkeypatch.setattr(help_text, "_SYSTEM", "linux")
    monkeypatch.setattr(help_text, "get_local_version", lambda: "9.9.9")

    help_text.print_help()

    captured = capfd.readouterr()
    assert "usb-tool 9.9.9" in captured.out
    assert "sudo usb -p 1" in captured.out
    assert "sudo usb -p /dev/sdb" in captured.out
    assert "OOB" in captured.out


def test_windows_and_linux_help_share_json_and_synopsis_format(capfd, monkeypatch):
    monkeypatch.setattr(help_text, "get_local_version", lambda: "1.2.3")

    monkeypatch.setattr(help_text, "_SYSTEM", "windows")
    help_text.print_help()
    windows_out = capfd.readouterr().out

    monkeypatch.setattr(help_text, "_SYSTEM", "linux")
    help_text.print_help()
    linux_out = capfd.readouterr().out

    for output in (windows_out, linux_out):
        assert "usb [-h] [-p TARGETS] [--json]" in output
        assert "--json" in output
        assert 'Emit JSON as {"devices":[{"<index>":{...}}]}' in output
