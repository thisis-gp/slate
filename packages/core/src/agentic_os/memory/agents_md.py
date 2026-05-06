from __future__ import annotations
import re
from dataclasses import dataclass, field

REQUIRED_SECTIONS = ["What", "Stack", "Commands", "Standards", "Do NOT"]


@dataclass
class BlueprintResult:
    valid: bool
    missing: list[str] = field(default_factory=list)
    token_estimate: int = 0


def validate_blueprint(content: str) -> BlueprintResult:
    missing = []
    for section in REQUIRED_SECTIONS:
        pattern = rf"##\s+{re.escape(section)}"
        if not re.search(pattern, content, re.IGNORECASE):
            missing.append(section)
    token_estimate = len(content.split()) * 4 // 3
    return BlueprintResult(valid=len(missing) == 0, missing=missing, token_estimate=token_estimate)


def generate_template(name: str, description: str, stack: str) -> str:
    return f"""# {name}

## What
{description}

## Stack
- {stack}

## Commands
- `<start command>` — Start development server
- `<test command>` — Run tests

## Standards
- Write type hints for all functions
- Write tests for all new features

## Do NOT
- Do NOT modify auth or payment code without review
- Do NOT commit secrets or API keys
- Do NOT use `any` types
"""
