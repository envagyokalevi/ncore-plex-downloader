"""A telepítési hibákat felismerő diagnosztika tesztjei."""

from __future__ import annotations

import pytest

from app.cli import describe_hash_problem
from app.security import hash_password

VALID = hash_password("valami-jelszo")


def test_valid_hash_has_no_problem() -> None:
    assert describe_hash_problem(VALID) is None


def test_empty_hash() -> None:
    problem = describe_hash_problem("")
    assert problem is not None and "üres" in problem


def test_placeholder_hash() -> None:
    assert describe_hash_problem("change-me") is not None


def test_duplicated_prefix_is_detected() -> None:
    """A leggyakoribb elgépelés: a CLI teljes sorát a régi mögé másolják."""
    problem = describe_hash_problem(f"ADMIN_PASSWORD_HASH={VALID}")
    assert problem is not None and "előtag" in problem


def test_lost_dollar_signs_are_detected() -> None:
    """Ha a $ jeleket változó-behelyettesítés nyeli el."""
    problem = describe_hash_problem(VALID.replace("$", ""))
    assert problem is not None and "bcrypt" in problem


def test_truncated_hash_is_detected() -> None:
    problem = describe_hash_problem(VALID[:30])
    assert problem is not None and "csonka" in problem


@pytest.mark.parametrize("value", ["jelszo123", "$1$valami", "nem-hash"])
def test_non_bcrypt_values_are_rejected(value: str) -> None:
    assert describe_hash_problem(value) is not None


def test_detected_problems_never_leak_the_hash() -> None:
    """A hibaüzenet nem tartalmazhatja magát a hash-t."""
    for candidate in ("", "change-me", VALID[:30], VALID.replace("$", "")):
        problem = describe_hash_problem(candidate)
        if problem and candidate:
            assert candidate not in problem
