import subprocess
import sys


def test_usb_tool_import_does_not_eager_import_windows_backend() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, usb_tool; print('usb_tool.backend.windows' in sys.modules)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "False"
