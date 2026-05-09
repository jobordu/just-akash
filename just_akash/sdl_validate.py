"""SDL validation for just-akash deployments.

Enforces project-level rules on Akash SDL files before submission to the
Console API.

Currently checks:
    - If any `profiles.placement.<name>.signedBy` clause is present, every
      address listed under `anyOf` / `allOf` must equal
      `AUDIT_AUTHORITY_ADDRESS`. The Akash chain only honors `signedBy`
      against this audit authority, so any other address silently disables
      the audit constraint and lets unaudited providers win bids.
"""

from __future__ import annotations

import yaml

AUDIT_AUTHORITY_ADDRESS = "akash1365yvmc4s7awdyj3n2sav7xfx76adc6dnmlx63"

_SIGNED_BY_CLAUSES = ("anyOf", "allOf")


class SDLValidationError(ValueError):
    """Raised when an SDL fails project-level validation."""


def validate_sdl(sdl_content: str) -> None:
    """Raise SDLValidationError if the SDL violates project rules.

    Returns None on success.
    """
    try:
        data = yaml.safe_load(sdl_content)
    except yaml.YAMLError as e:
        raise SDLValidationError(f"SDL is not valid YAML: {e}") from e

    if not isinstance(data, dict):
        raise SDLValidationError("SDL root must be a YAML mapping")

    errors: list[str] = []
    errors.extend(_check_signed_by(data))

    if errors:
        raise SDLValidationError("SDL validation failed:\n  - " + "\n  - ".join(errors))


def _check_signed_by(data: dict) -> list[str]:
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return []
    placement = profiles.get("placement")
    if not isinstance(placement, dict):
        return []

    errors: list[str] = []
    for name, profile in placement.items():
        if not isinstance(profile, dict):
            continue
        signed_by = profile.get("signedBy")
        if signed_by is None:
            continue
        path = f"profiles.placement.{name}.signedBy"

        if not isinstance(signed_by, dict):
            errors.append(f"{path} must be a mapping with 'anyOf' or 'allOf'")
            continue

        present = [c for c in _SIGNED_BY_CLAUSES if c in signed_by]
        if not present:
            errors.append(f"{path} must contain 'anyOf' or 'allOf'")
            continue

        for clause in present:
            addresses = signed_by.get(clause)
            if not isinstance(addresses, list) or not addresses:
                errors.append(f"{path}.{clause} must be a non-empty list of addresses")
                continue
            for addr in addresses:
                if addr != AUDIT_AUTHORITY_ADDRESS:
                    errors.append(
                        f"{path}.{clause} contains {addr!r}; "
                        f"only {AUDIT_AUTHORITY_ADDRESS!r} is allowed"
                    )
    return errors
