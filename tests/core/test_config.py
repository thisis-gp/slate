import pytest
from pathlib import Path
from agentic_os.config import Settings, RoleConfig, load_config

def test_load_default_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
version: "1"
providers:
  openrouter:
    api_key: "test-key"
    base_url: "https://openrouter.ai/api/v1"
  anthropic:
    api_key: "test-anthropic-key"
  nvidia:
    api_key: "test-nvidia-key"
    base_url: "https://integrate.api.nvidia.com/v1"
roles:
  cto:
    model: "anthropic/claude-opus-4-7"
    provider: "anthropic"
  sde1:
    model: "meta/llama-3.3-70b-instruct"
    provider: "nvidia"
budget:
  daily_limit_usd: 5.00
  alert_threshold: 0.80
server:
  host: "127.0.0.1"
  port: 7331
activation:
  level: "essential"
""")
    settings = load_config(config_file)
    assert settings.roles["cto"].model == "anthropic/claude-opus-4-7"
    assert settings.roles["cto"].provider == "anthropic"
    assert settings.budget.daily_limit_usd == 5.00
    assert settings.server.port == 7331

def test_role_config_has_required_fields():
    role = RoleConfig(model="test/model", provider="openrouter")
    assert role.model == "test/model"
    assert role.provider == "openrouter"

def test_missing_config_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.yaml"))
