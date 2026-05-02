from __future__ import annotations

from email_validator import EmailNotValidError, validate_email


def is_valid_email(addr: str, check_mx: bool = True) -> bool:
    """
    Validate an email address.

    Args:
        addr: The email address to validate.
        check_mx: Whether to check MX records for deliverability.

    Returns:
        True if the email is valid, False otherwise.
    """
    try:
        validate_email(addr, check_deliverability=check_mx)
        return True
    except EmailNotValidError:
        return False
