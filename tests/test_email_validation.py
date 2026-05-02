from __future__ import annotations

from plex_tg_bot.services.email import is_valid_email


class TestEmailValidation:
    def test_valid_email_no_mx(self) -> None:
        """Valid email passes when MX check is disabled."""
        assert is_valid_email("user@example.com", check_mx=False) is True

    def test_invalid_email_format(self) -> None:
        """Malformed email fails."""
        assert is_valid_email("not-an-email", check_mx=False) is False

    def test_invalid_email_empty(self) -> None:
        """Empty string fails."""
        assert is_valid_email("", check_mx=False) is False

    def test_invalid_email_no_at(self) -> None:
        """Email without @ fails."""
        assert is_valid_email("user.example.com", check_mx=False) is False
