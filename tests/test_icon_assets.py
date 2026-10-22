from __future__ import annotations

from importlib.resources import files


def test_application_icon_assets_are_present_and_valid() -> None:
    assets = files("jianyin_app").joinpath("assets")
    ico = assets.joinpath("jianyin.ico").read_bytes()
    png = assets.joinpath("jianyin.png").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00"
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    count = int.from_bytes(ico[4:6], "little")
    assert count >= 5
