import re

from plex_tg_bot import __version__


def test_version_present() -> None:
    assert re.match(r"^\d+\.\d+\.\d+$", __version__)
