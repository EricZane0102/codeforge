"""Workspace management for CodeForge.

Handles setting up the working directory for a challenge:
cloning/caching repos, checking out to the bug commit,
creating journal templates, and initializing session state.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from .config import (
    ensure_home,
    repo_cache_path,
    workspace_path,
    session_file,
    journal_file,
)
from .git_ops import clone_repo, fetch_commit, checkout, copy_repo, reset_hard
from .journal import create_journal_template
from .models import Challenge, Session, SessionStatus

console = Console()


def setup_workspace(challenge: Challenge) -> Path:
    """Set up a workspace for a challenge.

    This will:
    1. Clone or use cached repo
    2. Copy repo to workspace
    3. Checkout to base_commit (the buggy state)
    4. Create journal.md template
    5. Initialize session.json

    Args:
        challenge: The challenge to set up.

    Returns:
        Path to the workspace directory.

    Raises:
        RuntimeError: If workspace setup fails.
    """
    ensure_home()

    ws = workspace_path(challenge.id)
    sf = session_file(challenge.id)
    repo_dir = ws / "repo"

    # Check if already in progress
    if sf.exists():
        session = Session.load(sf)
        if session.status == SessionStatus.IN_PROGRESS:
            console.print(f"[yellow]⚠ 挑战 {challenge.id} 已经在进行中。[/yellow]")
            console.print(f"工作目录: {repo_dir}")
            return ws

    # Clone or use cache
    cache = repo_cache_path(challenge.repo)
    if cache.exists():
        console.print(f"[dim]使用缓存仓库 {challenge.repo}...[/dim]")
    else:
        console.print(f"[bold]首次下载仓库 {challenge.repo}...[/bold]")
        clone_repo(challenge.repo, cache, shallow=True)

    # Fetch the required commits
    fetch_commit(cache, challenge.setup.base_commit)
    fetch_commit(cache, challenge.setup.solution_commit)

    # Copy to workspace
    if repo_dir.exists():
        console.print("[dim]清理旧工作目录...[/dim]")
        import shutil
        shutil.rmtree(repo_dir)

    ws.mkdir(parents=True, exist_ok=True)
    copy_repo(cache, repo_dir)

    # Checkout to the buggy commit
    checkout(repo_dir, challenge.setup.base_commit)
    reset_hard(repo_dir, challenge.setup.base_commit)

    # Create journal template
    jf = journal_file(challenge.id)
    create_journal_template(jf, challenge)

    # Initialize session
    session = Session(challenge_id=challenge.id)
    session.start()
    session.save(sf)

    # Create submission directory
    (ws / "submission").mkdir(exist_ok=True)

    return ws


def display_challenge_info(challenge: Challenge) -> None:
    """Display challenge information in a nice panel.

    Args:
        challenge: The challenge to display.
    """
    difficulty_colors = {
        "easy": "green",
        "medium": "yellow",
        "hard": "red",
    }
    color = difficulty_colors.get(challenge.difficulty.value, "white")

    info_lines = [
        f"**仓库**: `{challenge.repo}`",
        f"**难度**: {challenge.difficulty.value}",
        f"**时限**: {challenge.time_limit} 分钟",
        "",
        "---",
        "",
        challenge.description.strip(),
    ]

    if challenge.setup.files_of_interest:
        info_lines.append("")
        info_lines.append("**关注文件**:")
        for f in challenge.setup.files_of_interest:
            info_lines.append(f"- `{f}`")

    if challenge.tags:
        info_lines.append("")
        info_lines.append(f"**标签**: {', '.join(challenge.tags)}")

    md = Markdown("\n".join(info_lines))
    panel = Panel(
        md,
        title=f"[bold {color}]🔥 {challenge.title}[/bold {color}]",
        subtitle=f"[dim]{challenge.id}[/dim]",
        border_style=color,
        padding=(1, 2),
    )
    console.print(panel)


def get_active_session(challenge_id: str) -> Session | None:
    """Get the active session for a challenge, if any.

    Args:
        challenge_id: The challenge identifier.

    Returns:
        The Session if it exists, None otherwise.
    """
    sf = session_file(challenge_id)
    if not sf.exists():
        return None
    return Session.load(sf)
