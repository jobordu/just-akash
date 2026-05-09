"""Tests for just_akash.sdl_validate — SDL validation rules."""

import pytest

from just_akash.sdl_validate import (
    AUDIT_AUTHORITY_ADDRESS,
    SDLValidationError,
    validate_sdl,
)

GOOD = AUDIT_AUTHORITY_ADDRESS
BAD = "akash1baadbaadbaadbaadbaadbaadbaadbaadbaadbaad"


def _sdl(placement_block: str) -> str:
    return f"""
version: "2.0"
services:
  web:
    image: nginx
    expose:
      - port: 80
        as: 80
        to:
          - global: true
profiles:
  compute:
    web:
      resources:
        cpu:
          units: 1
        memory:
          size: 512Mi
        storage:
          - size: 1Gi
  placement:
{placement_block}
deployment:
  web:
    akash:
      profile: web
      count: 1
"""


def test_no_signed_by_passes():
    sdl = _sdl(
        """    akash:
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    validate_sdl(sdl)


def test_correct_any_of_passes():
    sdl = _sdl(
        f"""    akash:
      signedBy:
        anyOf:
          - {GOOD}
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    validate_sdl(sdl)


def test_correct_all_of_passes():
    sdl = _sdl(
        f"""    akash:
      signedBy:
        allOf:
          - {GOOD}
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    validate_sdl(sdl)


def test_wrong_address_fails():
    sdl = _sdl(
        f"""    akash:
      signedBy:
        anyOf:
          - {BAD}
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    with pytest.raises(SDLValidationError) as exc:
        validate_sdl(sdl)
    assert BAD in str(exc.value)
    assert GOOD in str(exc.value)


def test_mixed_list_one_bad_fails():
    sdl = _sdl(
        f"""    akash:
      signedBy:
        anyOf:
          - {GOOD}
          - {BAD}
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    with pytest.raises(SDLValidationError) as exc:
        validate_sdl(sdl)
    assert BAD in str(exc.value)


def test_empty_any_of_fails():
    sdl = _sdl(
        """    akash:
      signedBy:
        anyOf: []
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    with pytest.raises(SDLValidationError, match="non-empty list"):
        validate_sdl(sdl)


def test_signed_by_without_any_or_all_of_fails():
    sdl = _sdl(
        """    akash:
      signedBy:
        unknown: foo
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    with pytest.raises(SDLValidationError, match="must contain 'anyOf' or 'allOf'"):
        validate_sdl(sdl)


def test_signed_by_not_a_mapping_fails():
    sdl = _sdl(
        f"""    akash:
      signedBy: {GOOD}
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    with pytest.raises(SDLValidationError, match="must be a mapping"):
        validate_sdl(sdl)


def test_multiple_placements_all_checked():
    sdl = _sdl(
        f"""    akash:
      signedBy:
        anyOf:
          - {GOOD}
      pricing:
        web:
          denom: uakt
          amount: 1000
    dcloud:
      signedBy:
        anyOf:
          - {BAD}
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    with pytest.raises(SDLValidationError) as exc:
        validate_sdl(sdl)
    msg = str(exc.value)
    assert "dcloud" in msg
    assert BAD in msg


def test_flow_style_caught():
    # Flow-style YAML — line-based parsing would miss this; PyYAML catches it.
    sdl = _sdl(
        f"""    akash:
      signedBy: {{anyOf: [{BAD}]}}
      pricing:
        web:
          denom: uakt
          amount: 1000
"""
    )
    with pytest.raises(SDLValidationError) as exc:
        validate_sdl(sdl)
    assert BAD in str(exc.value)


def test_invalid_yaml_fails():
    with pytest.raises(SDLValidationError, match="not valid YAML"):
        validate_sdl("version: '2.0'\n  bad: indentation\n :::: nope")


def test_root_not_mapping_fails():
    with pytest.raises(SDLValidationError, match="must be a YAML mapping"):
        validate_sdl("- just\n- a\n- list")


def test_repo_sdl_passes():
    """The shipped sdl/cpu-backtest-ssh.yaml has no signedBy, so it should pass."""
    from pathlib import Path

    sdl = Path(__file__).resolve().parent.parent / "sdl" / "cpu-backtest-ssh.yaml"
    validate_sdl(sdl.read_text())
