"""Types for optional numeric filters submitted by GET forms."""
from typing import Annotated

from pydantic import BeforeValidator


def blank_to_none(value):
    """Only an empty selection is missing; keep invalid values for validation."""
    return None if isinstance(value, str) and not value.strip() else value


OptionalQueryInt = Annotated[int | None, BeforeValidator(blank_to_none)]
