import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "build" / "check_glibc_floor.py"
SPEC = importlib.util.spec_from_file_location("check_glibc_floor", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
check_glibc_floor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_glibc_floor)


def test_parse_glibc_versions_deduplicates_and_sorts() -> None:
    text = """
    0000000000000000      DF *UND*  0000000000000000 (GLIBC_2.14) memcpy
    0000000000000000      DF *UND*  0000000000000000 (GLIBC_2.2.5) close
    0000000000000000      DF *UND*  0000000000000000 (GLIBC_2.31) pthread_getname_np
    0000000000000000      DF *UND*  0000000000000000 (GLIBC_2.14) memcpy
    """

    assert check_glibc_floor.parse_glibc_versions(text) == [
        (2, 2, 5),
        (2, 14),
        (2, 31),
    ]


def test_max_glibc_version_returns_highest_seen_version() -> None:
    text = """
    Name: GLIBC_2.17  Flags: none  Version: 10
    Name: GLIBC_2.28  Flags: none  Version: 7
    Name: GLIBC_2.31  Flags: none  Version: 3
    """

    assert check_glibc_floor.max_glibc_version(text) == (2, 31)
    assert check_glibc_floor.format_version((2, 31)) == "2.31"
