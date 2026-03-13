import os
import subprocess
import sys
from pathlib import Path


def test_usb_tool_import_does_not_eager_import_windows_backend() -> None:
    repo_src = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{repo_src}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(repo_src)
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, usb_tool; print('usb_tool.backend.windows' in sys.modules)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout.strip() == "False"
