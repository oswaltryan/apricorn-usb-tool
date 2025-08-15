from usb_tool import utils


def test_bytes_to_gb():
    """bytes_to_gb converts bytes to gigabytes and handles bad input."""
    assert utils.bytes_to_gb(1024**3) == 1.0
    assert utils.bytes_to_gb(-1) == 0.0


def test_find_closest():
    """find_closest returns the nearest option to the target."""
    assert utils.find_closest(6, [1, 7, 10]) == 7
    assert utils.find_closest(-1, [1, 2]) is None


def test_parse_usb_version():
    """parse_usb_version converts BCD values to strings."""
    assert utils.parse_usb_version(0x0310) == "3.1"
    assert utils.parse_usb_version(0x0211) == "2.11"
