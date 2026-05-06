from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel


class ProviderConfig(BaseModel):
    api_key: str
    base_url: str = ""


class RoleConfig(BaseModel):
    model: str
    provider: str


class BudgetConfig(BaseModel):
    daily_limit_usd: float = 5.0
    alert_threshold: float = 0.8


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 7331


class ActivationConfig(BaseModel):
    level: str = "essential"


class Settings(BaseModel):
    version: str = "1"
    providers: dict[str, ProviderConfig] = {}
    roles: dict[str, RoleConfig] = {}
    budget: BudgetConfig = BudgetConfig()
    server: ServerConfig = ServerConfig()
    activation: ActivationConfig = ActivationConfig()


def load_config(path: Path) -> Settings:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    return Settings.model_validate(raw)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        config_path = Path(".agentic-os/config.yaml")
        if not config_path.exists():
            config_path = Path.home() / ".agentic-os" / "config.yaml"
        _settings = load_config(config_path)
    return _settings
