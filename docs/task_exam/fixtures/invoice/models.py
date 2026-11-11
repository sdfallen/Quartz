from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    unit_cents: int
    quantity: int
