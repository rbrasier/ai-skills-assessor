"""Phone-number normalisation for outbound dialling.

The candidate intake form accepts loose international formats
("+44 7700 900118", "44 7700 900118", "+61 (4) 1234-5678"). The voice
engine always dials E.164 (``+`` followed by digits), so all entry
points should normalise before persisting or dialling.

This helper lives in the domain layer because the rule is business
logic — adapters and API routes should call it rather than each
implementing their own normalisation.
"""

from __future__ import annotations

# Minimum digit count for an E.164 number (country code + subscriber).
# 7 is the absolute minimum allowed by E.164; we use 8 as a sanity
# floor for international dialling (country code + at least 6 digits).
_MIN_DIGITS = 8
_MAX_DIGITS = 15  # E.164 upper bound.


class InvalidPhoneNumberError(ValueError):
    """Raised when a phone number cannot be normalised to E.164."""


def normalise_phone_number(raw: str) -> str:
    """Return ``raw`` as an E.164 string (``+`` + digits).

    Accepts:
      * ``+`` prefix (preserved)
      * Spaces, hyphens, parentheses, dots (stripped)
      * Leading ``00`` international prefix (converted to ``+``)

    Raises ``InvalidPhoneNumberError`` if the result is empty or has
    fewer than :data:`_MIN_DIGITS` / more than :data:`_MAX_DIGITS`
    digits.
    """

    if not raw or not raw.strip():
        raise InvalidPhoneNumberError("phone number is empty")

    stripped = raw.strip()
    had_plus = stripped.startswith("+")
    digits = "".join(c for c in stripped if c.isdigit())

    if not digits:
        raise InvalidPhoneNumberError("phone number contains no digits")

    # Treat a leading "00" (international direct-dial prefix in many
    # countries) as equivalent to a leading "+".
    if not had_plus and digits.startswith("00"):
        digits = digits[2:]
        had_plus = True

    if len(digits) < _MIN_DIGITS:
        raise InvalidPhoneNumberError(
            f"phone number too short: {len(digits)} digits (min {_MIN_DIGITS})"
        )
    if len(digits) > _MAX_DIGITS:
        raise InvalidPhoneNumberError(
            f"phone number too long: {len(digits)} digits (max {_MAX_DIGITS})"
        )

    # We always emit E.164 (leading ``+``). ``had_plus`` is retained above
    # for future expansion (e.g. rejecting numbers that lack a country
    # code) but does not currently change the output shape.
    del had_plus
    return f"+{digits}"
