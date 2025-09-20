"""Configuration management for RQL.

Handles loading and merging configuration from:
1. Global config file (~/.rql/config.toml)
2. Local project config file (./rql.toml)
3. Environment variables
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import toml
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = "google-genai"
    model: str = "gemini-2.5-flash"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    api_key: Optional[str] = None  # Direct API key storage
    api_key_env: str = "GEMINI_API_KEY"  # Fallback to env var


class WorkflowConfig(BaseModel):
    """Workflow executor configuration."""
    default_timeout: int = 30
    max_retries: int = 3


class TracingConfig(BaseModel):
    """Execution tracing configuration."""
    enabled: bool = True
    trace_dir: str = "~/.rql/runs"
    include_costs: bool = True
    include_performance: bool = True


class RQLConfig(BaseModel):
    """Main RQL configuration."""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)

    # Session defaults
    output_format: str = "json"
    verbose: bool = False


def get_config_path(local: bool = False) -> Path:
    """Get the path to the configuration file."""
    if local:
        return Path("./rql.toml")
    else:
        return Path.home() / ".rql" / "config.toml"


def load_config() -> RQLConfig:
    """Load configuration from files and environment variables."""
    config_data: Dict[str, Any] = {}

    # Load global config
    global_config_path = get_config_path(local=False)
    if global_config_path.exists():
        with open(global_config_path, "r") as f:
            global_config = toml.load(f)
            config_data.update(global_config)

    # Load local config (overrides global)
    local_config_path = get_config_path(local=True)
    if local_config_path.exists():
        with open(local_config_path, "r") as f:
            local_config = toml.load(f)
            config_data.update(local_config)

    # Override with environment variables
    if "GEMINI_API_KEY" in os.environ:
        if "llm" not in config_data:
            config_data["llm"] = {}
        config_data["llm"]["api_key_env"] = "GEMINI_API_KEY"

    # Override tracing directory from environment
    if "RQL_TRACE_DIR" in os.environ:
        if "tracing" not in config_data:
            config_data["tracing"] = {}
        config_data["tracing"]["trace_dir"] = os.environ["RQL_TRACE_DIR"]

    return RQLConfig(**config_data)


def ensure_config_dir() -> None:
    """Ensure the RQL configuration directory exists."""
    config_dir = Path.home() / ".rql"
    config_dir.mkdir(exist_ok=True)

    # Create runs directory for tracing
    runs_dir = config_dir / "runs"
    runs_dir.mkdir(exist_ok=True)


def create_default_config() -> None:
    """Create a default configuration file."""
    config_path = get_config_path(local=False)
    ensure_config_dir()

    if not config_path.exists():
        default_config = {
            "llm": {
                "provider": "google-genai",
                "model": "gemini-2.5-flash",
                "temperature": 0.7,
                "api_key": "YOUR_API_KEY_HERE",
                "api_key_env": "GEMINI_API_KEY"
            },
            "workflow": {
                "default_timeout": 30,
                "max_retries": 3
            },
            "tracing": {
                "enabled": True,
                "trace_dir": "~/.rql/runs",
                "include_costs": True,
                "include_performance": True
            },
            "output_format": "json",
            "verbose": False
        }

        with open(config_path, "w") as f:
            toml.dump(default_config, f)