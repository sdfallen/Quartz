"""Validated screen target representation and confirmation-safe clicking."""

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenTarget:
    target: str
    x: int
    y: int
    confidence: float
    description: str
    preview_path: str = ""


def parse_target_json(text: str, width: int, height: int, target: str) -> ScreenTarget:
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        raise ValueError("Vision model did not return target coordinates")
    data = json.loads(match.group(0))
    nx, ny = int(data["x"]), int(data["y"])
    confidence = float(data.get("confidence", 0))
    if not (0 <= nx <= 1000 and 0 <= ny <= 1000):
        raise ValueError("Target coordinates are outside the screen")
    if nx <= 3 or ny <= 3 or nx >= 997 or ny >= 997:
        raise ValueError("Target coordinates are implausibly close to a screen edge")
    if not (0 <= confidence <= 1):
        raise ValueError("Target confidence must be between 0 and 1")
    return ScreenTarget(
        target=target, x=round(nx * width / 1000), y=round(ny * height / 1000),
        confidence=confidence, description=str(data.get("description", target)),
    )
