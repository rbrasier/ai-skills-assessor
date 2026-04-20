"""Unit tests for the phone-number normalisation helper."""

from __future__ import annotations

import pytest

from src.domain.utils.phone import InvalidPhoneNumberError, normalise_phone_number


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+61412345678", "+61412345678"),
        ("44 7700 900118", "+447700900118"),
        ("+44 7700 900118", "+447700900118"),
        ("+1 (415) 555-2671", "+14155552671"),
        ("00447700900118", "+447700900118"),
    ],
)
def test_normalise_common_formats(raw: str, expected: str) -> None:
    assert normalise_phone_number(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "abc", "+", "+1234", "+12345678901234567"])
def test_normalise_rejects_bad_inputs(bad: str) -> None:
    with pytest.raises(InvalidPhoneNumberError):
        normalise_phone_number(bad)
