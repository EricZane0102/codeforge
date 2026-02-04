"""Challenge management for CodeForge.

Loads challenges from YAML files in both the built-in challenges
directory and the user's ~/.codeforge/challenges/ directory.
"""

from __future__ import annotations

import importlib.resources
import random
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from rich.table import Table

from .config import CHALLENGES_DIR, session_file
from .models import Challenge, Difficulty, Session, SessionStatus

console = Console()


def _load_yaml_challenges(directory: Path) -> list[Challenge]:
    """Load all challenge YAML files from a directory.

    Args:
        directory: Path to scan for .yaml/.yml files.

    Returns:
        List of loaded Challenge objects.
    """
    challenges = []
    if not directory.exists():
        return challenges

    for f in sorted(directory.iterdir()):
        if f.suffix in (".yaml", ".yml"):
            try:
                with open(f) as fh:
                    data = yaml.safe_load(fh)
                if data:
                    challenges.append(Challenge.from_dict(data))
            except (yaml.YAMLError, KeyError, ValueError) as e:
                console.print(f"[yellow]⚠ 跳过 {f.name}: {e}[/yellow]")
    return challenges


def load_builtin_challenges() -> list[Challenge]:
    """Load challenges bundled with the package.

    Returns:
        List of built-in Challenge objects.
    """
    try:
        pkg_dir = importlib.resources.files("codeforge") / "challenges"
        # Convert to Path for consistent handling
        challenges_path = Path(str(pkg_dir))
        return _load_yaml_challenges(challenges_path)
    except (TypeError, FileNotFoundError):
        return []


def load_all_challenges() -> list[Challenge]:
    """Load all available challenges (built-in + user-defined).

    User-defined challenges in ~/.codeforge/challenges/ override
    built-in ones with the same ID.

    Returns:
        List of all available Challenge objects.
    """
    # Start with built-in challenges
    challenges_by_id: dict[str, Challenge] = {}

    for c in load_builtin_challenges():
        challenges_by_id[c.id] = c

    # User challenges override built-in ones
    for c in _load_yaml_challenges(CHALLENGES_DIR):
        challenges_by_id[c.id] = c

    return list(challenges_by_id.values())


def get_challenge(challenge_id: str) -> Optional[Challenge]:
    """Get a specific challenge by ID.

    Args:
        challenge_id: The challenge identifier.

    Returns:
        The Challenge if found, None otherwise.
    """
    for c in load_all_challenges():
        if c.id == challenge_id:
            return c
    return None


def get_session_status(challenge_id: str) -> SessionStatus:
    """Get the status of a challenge session.

    Args:
        challenge_id: The challenge identifier.

    Returns:
        The session status.
    """
    sf = session_file(challenge_id)
    if not sf.exists():
        return SessionStatus.NOT_STARTED
    try:
        session = Session.load(sf)
        return session.status
    except (KeyError, ValueError):
        return SessionStatus.NOT_STARTED


def pick_challenge(
    difficulty: Optional[Difficulty] = None,
    challenge_id: Optional[str] = None,
) -> Optional[Challenge]:
    """Pick a challenge to work on.

    Args:
        difficulty: Optional difficulty filter.
        challenge_id: Optional specific challenge ID.

    Returns:
        A Challenge, or None if nothing matches.
    """
    if challenge_id:
        return get_challenge(challenge_id)

    challenges = load_all_challenges()

    if difficulty:
        challenges = [c for c in challenges if c.difficulty == difficulty]

    # Filter out completed ones
    incomplete = [
        c for c in challenges
        if get_session_status(c.id) not in (SessionStatus.SUBMITTED, SessionStatus.REVIEWED)
    ]

    if not incomplete:
        # If all are completed at the given difficulty, return any uncompleted
        incomplete = [
            c for c in load_all_challenges()
            if get_session_status(c.id) not in (SessionStatus.SUBMITTED, SessionStatus.REVIEWED)
        ]

    if not incomplete:
        return None

    return random.choice(incomplete)


def display_challenge_list() -> None:
    """Display a formatted table of all available challenges."""
    challenges = load_all_challenges()

    if not challenges:
        console.print("[yellow]没有找到可用的挑战。[/yellow]")
        console.print("运行 [bold]forge init[/bold] 初始化，或添加 YAML 文件到 ~/.codeforge/challenges/")
        return

    table = Table(title="🔥 CodeForge 挑战列表", show_lines=True)
    table.add_column("ID", style="cyan", min_width=15)
    table.add_column("标题", style="white", min_width=30)
    table.add_column("难度", min_width=8)
    table.add_column("时限", justify="right", min_width=6)
    table.add_column("状态", min_width=10)
    table.add_column("标签", style="dim")

    difficulty_colors = {
        Difficulty.EASY: "green",
        Difficulty.MEDIUM: "yellow",
        Difficulty.HARD: "red",
    }

    status_icons = {
        SessionStatus.NOT_STARTED: "⬜ 未开始",
        SessionStatus.IN_PROGRESS: "🔵 进行中",
        SessionStatus.SUBMITTED: "✅ 已提交",
        SessionStatus.REVIEWED: "⭐ 已评判",
    }

    for c in challenges:
        status = get_session_status(c.id)
        color = difficulty_colors.get(c.difficulty, "white")
        table.add_row(
            c.id,
            c.title,
            f"[{color}]{c.difficulty.value}[/{color}]",
            f"{c.time_limit}min",
            status_icons.get(status, "❓"),
            ", ".join(c.tags),
        )

    console.print(table)
