import pytest
from agentic_os.memory.agents_md import validate_blueprint, generate_template, BlueprintResult

def test_valid_agents_md_passes():
    content = """
# MyProject
## What
A web API for managing user tasks.

## Stack
- Python 3.11, FastAPI, PostgreSQL

## Commands
- `uvicorn main:app --reload` — Start dev server
- `pytest` — Run tests

## Standards
- Use type hints everywhere
- Write tests for all endpoints

## Do NOT
- Do NOT modify the users table schema directly
- Do NOT commit secrets
"""
    result = validate_blueprint(content)
    assert result.valid is True
    assert len(result.missing) == 0

def test_missing_sections_caught():
    content = """
# MyProject
## What
A web API.
"""
    result = validate_blueprint(content)
    assert result.valid is False
    assert "Stack" in result.missing
    assert "Commands" in result.missing
    assert "Standards" in result.missing
    assert "Do NOT" in result.missing

def test_template_has_all_sections():
    template = generate_template("TestProject", "A test project", "Python, FastAPI")
    result = validate_blueprint(template)
    assert result.valid is True

def test_token_estimate_reasonable():
    template = generate_template("TestProject", "A test project", "Python")
    result = validate_blueprint(template)
    assert result.token_estimate < 500
