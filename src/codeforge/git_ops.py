"""Git operations for CodeForge.

All git operations use subprocess to call the git CLI directly.
No external git libraries (like gitpython) are used.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


class GitError(Exception):
    """Raised when a git operation fails."""
    pass


def _run_git(
    args: list[str],
    cwd: Optional[Path] = None,
    capture: bool = True,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    """Run a git command.

    Args:
        args: Git command arguments (without 'git' prefix).
        cwd: Working directory.
        capture: Whether to capture output.
        timeout: Command timeout in seconds.

    Returns:
        CompletedProcess result.

    Raises:
        GitError: If the command fails.
    """
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0 and capture:
            stderr = result.stderr.strip()
            raise GitError(f"git {' '.join(args)} 失败: {stderr}")
        return result
    except subprocess.TimeoutExpired:
        raise GitError(f"git {' '.join(args)} 超时 ({timeout}s)")
    except FileNotFoundError:
        raise GitError("找不到 git 命令，请确保 git 已安装")


def clone_repo(repo: str, dest: Path, shallow: bool = True) -> None:
    """Clone a GitHub repository.

    Args:
        repo: GitHub repo in 'owner/name' format.
        dest: Destination directory.
        shallow: Whether to do a shallow clone (faster).

    Raises:
        GitError: If cloning fails.
    """
    url = f"https://github.com/{repo}.git"
    args = ["clone"]
    if shallow:
        args.extend(["--depth", "1", "--no-single-branch"])
    args.extend([url, str(dest)])

    console.print(f"[dim]Cloning {repo}...[/dim]")
    _run_git(args, timeout=600)


def fetch_commit(repo_path: Path, commit: str) -> None:
    """Fetch a specific commit (useful for shallow clones).

    Args:
        repo_path: Path to the repository.
        commit: The commit hash to fetch.

    Raises:
        GitError: If fetching fails.
    """
    try:
        # Check if commit already exists locally
        _run_git(["cat-file", "-t", commit], cwd=repo_path)
    except GitError:
        # Need to unshallow or fetch the specific commit
        console.print(f"[dim]Fetching commit {commit[:8]}...[/dim]")
        try:
            _run_git(["fetch", "origin", commit], cwd=repo_path, timeout=600)
        except GitError:
            # If specific fetch fails, try unshallowing
            console.print("[dim]Unshallowing repository...[/dim]")
            _run_git(["fetch", "--unshallow"], cwd=repo_path, timeout=600)


def checkout(repo_path: Path, commit: str) -> None:
    """Checkout a specific commit.

    Args:
        repo_path: Path to the repository.
        commit: The commit hash or ref to checkout.

    Raises:
        GitError: If checkout fails.
    """
    _run_git(["checkout", commit, "--force"], cwd=repo_path)


def get_diff(repo_path: Path, staged: bool = False) -> str:
    """Get the current diff in a repository.

    Args:
        repo_path: Path to the repository.
        staged: Whether to show staged changes only.

    Returns:
        The diff output as a string.
    """
    args = ["diff"]
    if staged:
        args.append("--staged")
    result = _run_git(args, cwd=repo_path)
    return result.stdout


def get_diff_between(repo_path: Path, from_commit: str, to_commit: str) -> str:
    """Get the diff between two commits.

    Args:
        repo_path: Path to the repository.
        from_commit: The base commit.
        to_commit: The target commit.

    Returns:
        The diff output as a string.
    """
    result = _run_git(["diff", from_commit, to_commit], cwd=repo_path)
    return result.stdout


def get_all_changes(repo_path: Path) -> str:
    """Get all changes (staged + unstaged) compared to HEAD.

    Args:
        repo_path: Path to the repository.

    Returns:
        The diff output as a string.
    """
    # Get both staged and unstaged changes
    result = _run_git(["diff", "HEAD"], cwd=repo_path)
    return result.stdout


def has_changes(repo_path: Path) -> bool:
    """Check if the repo has any uncommitted changes.

    Args:
        repo_path: Path to the repository.

    Returns:
        True if there are changes.
    """
    result = _run_git(["status", "--porcelain"], cwd=repo_path)
    return bool(result.stdout.strip())


def reset_hard(repo_path: Path, commit: str = "HEAD") -> None:
    """Hard reset to a commit.

    Args:
        repo_path: Path to the repository.
        commit: The commit to reset to.
    """
    _run_git(["reset", "--hard", commit], cwd=repo_path)
    _run_git(["clean", "-fd"], cwd=repo_path)


def copy_repo(src: Path, dest: Path) -> None:
    """Copy a cached repo to a workspace using cp -a.

    Args:
        src: Source repo directory.
        dest: Destination directory.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cp", "-a", str(src), str(dest)],
        check=True,
    )
