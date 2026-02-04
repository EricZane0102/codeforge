"""Configuration management for CodeForge.

Handles ~/.codeforge/ directory structure, config.yaml read/write,
and path resolution for workspaces, repos, challenges, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from rich.console import Console

console = Console()

# Default paths
CODEFORGE_HOME = Path.home() / ".codeforge"
CONFIG_FILE = CODEFORGE_HOME / "config.yaml"
CHALLENGES_DIR = CODEFORGE_HOME / "challenges"
REPOS_DIR = CODEFORGE_HOME / "repos"
WORKSPACES_DIR = CODEFORGE_HOME / "workspaces"
HISTORY_FILE = CODEFORGE_HOME / "history.json"

# Default config values
DEFAULT_CONFIG: dict[str, Any] = {
    "editor": "vim",
    "api_provider": None,  # "anthropic" or "openai"
    "api_key": None,
    "api_model": None,
    "time_warnings": True,
    "auto_test": True,
}


def ensure_home() -> Path:
    """Ensure ~/.codeforge/ directory structure exists.

    Creates the home directory and all standard subdirectories
    if they don't already exist.

    Returns:
        Path to the codeforge home directory.
    """
    for d in [CODEFORGE_HOME, CHALLENGES_DIR, REPOS_DIR, WORKSPACES_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    return CODEFORGE_HOME


def load_config() -> dict[str, Any]:
    """Load configuration from config.yaml.

    Returns:
        Configuration dictionary, merged with defaults.
    """
    config = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                user_config = yaml.safe_load(f) or {}
            config.update(user_config)
        except yaml.YAMLError as e:
            console.print(f"[yellow]⚠ config.yaml 解析失败: {e}[/yellow]")
    return config


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to config.yaml.

    Args:
        config: Configuration dictionary to save.
    """
    ensure_home()
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def get_config_value(key: str) -> Optional[Any]:
    """Get a single configuration value.

    Args:
        key: Configuration key name.

    Returns:
        The value, or None if not set.
    """
    config = load_config()
    return config.get(key)


def set_config_value(key: str, value: Any) -> None:
    """Set a single configuration value and save.

    Args:
        key: Configuration key name.
        value: Value to set.
    """
    config = load_config()
    config[key] = value
    save_config(config)


def workspace_path(challenge_id: str) -> Path:
    """Get the workspace directory for a challenge.

    Args:
        challenge_id: The challenge identifier.

    Returns:
        Path to the workspace directory.
    """
    return WORKSPACES_DIR / challenge_id


def session_file(challenge_id: str) -> Path:
    """Get the session.json path for a challenge.

    Args:
        challenge_id: The challenge identifier.

    Returns:
        Path to the session.json file.
    """
    return workspace_path(challenge_id) / "session.json"


def journal_file(challenge_id: str) -> Path:
    """Get the journal.md path for a challenge.

    Args:
        challenge_id: The challenge identifier.

    Returns:
        Path to the journal.md file.
    """
    return workspace_path(challenge_id) / "journal.md"


def repo_cache_path(repo: str) -> Path:
    """Get the cached repo path for a GitHub repo.

    Args:
        repo: GitHub repo in 'owner/name' format.

    Returns:
        Path to the cached repo directory.
    """
    return REPOS_DIR / repo.replace("/", "__")


def submission_dir(challenge_id: str) -> Path:
    """Get the submission directory for a challenge.

    Args:
        challenge_id: The challenge identifier.

    Returns:
        Path to the submission directory.
    """
    return workspace_path(challenge_id) / "submission"
