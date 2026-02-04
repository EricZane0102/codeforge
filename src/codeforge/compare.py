"""Compare system for CodeForge.

Displays the user's diff side-by-side (or sequentially) with
the real solution diff, using Rich for syntax highlighting.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.columns import Columns
from rich.text import Text

from .config import session_file, workspace_path
from .git_ops import get_diff_between, fetch_commit
from .models import Challenge, Session, SessionStatus

console = Console()


def compare_solutions(challenge: Challenge, side_by_side: bool = False) -> bool:
    """Compare user's solution with the real solution.

    Args:
        challenge: The challenge to compare.
        side_by_side: Whether to display side-by-side (default: sequential).

    Returns:
        True if comparison succeeded.
    """
    sf = session_file(challenge.id)

    if not sf.exists():
        console.print("[red]❌ 没有找到会话记录。请先完成并提交挑战。[/red]")
        return False

    session = Session.load(sf)

    if session.status not in (SessionStatus.SUBMITTED, SessionStatus.REVIEWED):
        console.print("[red]❌ 请先提交你的方案（forge submit）再查看对比。[/red]")
        return False

    # Get user's diff
    user_diff = session.user_diff
    if not user_diff:
        console.print("[yellow]⚠ 没有找到你的代码改动。[/yellow]")
        user_diff = "(无改动)"

    # Get solution diff
    repo_dir = workspace_path(challenge.id) / "repo"
    solution_diff = _get_solution_diff(challenge, repo_dir)

    if not solution_diff:
        console.print("[yellow]⚠ 无法获取真实解法。[/yellow]")
        solution_diff = "(无法获取)"

    # Save solution diff to session
    session.solution_diff = solution_diff
    session.save(sf)

    # Display
    if side_by_side:
        _display_side_by_side(user_diff, solution_diff)
    else:
        _display_sequential(user_diff, solution_diff)

    # Show summary of differences
    _show_diff_summary(user_diff, solution_diff)

    return True


def _get_solution_diff(challenge: Challenge, repo_dir: any) -> str:
    """Get the real solution diff between base and solution commits.

    Args:
        challenge: The challenge.
        repo_dir: Path to the repo directory.

    Returns:
        The solution diff as a string.
    """
    try:
        fetch_commit(repo_dir, challenge.setup.solution_commit)
        return get_diff_between(
            repo_dir,
            challenge.setup.base_commit,
            challenge.setup.solution_commit,
        )
    except Exception as e:
        console.print(f"[yellow]⚠ 获取解法 diff 失败: {e}[/yellow]")
        return ""


def _display_sequential(user_diff: str, solution_diff: str) -> None:
    """Display diffs sequentially (one after the other).

    Args:
        user_diff: The user's diff.
        solution_diff: The real solution diff.
    """
    console.print()

    # User's diff
    user_syntax = Syntax(
        user_diff[:5000],  # Truncate very long diffs
        "diff",
        theme="monokai",
        line_numbers=True,
    )
    console.print(Panel(
        user_syntax,
        title="[bold cyan]🔧 你的改动[/bold cyan]",
        border_style="cyan",
    ))

    console.print()

    # Solution diff
    sol_syntax = Syntax(
        solution_diff[:5000],
        "diff",
        theme="monokai",
        line_numbers=True,
    )
    console.print(Panel(
        sol_syntax,
        title="[bold green]✅ 真实解法[/bold green]",
        border_style="green",
    ))


def _display_side_by_side(user_diff: str, solution_diff: str) -> None:
    """Display diffs side by side.

    Args:
        user_diff: The user's diff.
        solution_diff: The real solution diff.
    """
    console.print()

    user_panel = Panel(
        Syntax(user_diff[:3000], "diff", theme="monokai"),
        title="[bold cyan]🔧 你的改动[/bold cyan]",
        border_style="cyan",
    )

    sol_panel = Panel(
        Syntax(solution_diff[:3000], "diff", theme="monokai"),
        title="[bold green]✅ 真实解法[/bold green]",
        border_style="green",
    )

    console.print(Columns([user_panel, sol_panel], equal=True))


def _show_diff_summary(user_diff: str, solution_diff: str) -> None:
    """Show a brief summary comparing the two diffs.

    Args:
        user_diff: The user's diff.
        solution_diff: The real solution diff.
    """
    user_files = _extract_diff_files(user_diff)
    sol_files = _extract_diff_files(solution_diff)

    console.print()
    summary = Text()
    summary.append("📊 对比摘要\n\n", style="bold")

    # Files changed
    summary.append(f"你改动的文件: ", style="dim")
    summary.append(f"{', '.join(user_files) if user_files else '无'}\n", style="cyan")
    summary.append(f"真实解法文件: ", style="dim")
    summary.append(f"{', '.join(sol_files) if sol_files else '无'}\n", style="green")

    # Common files
    common = set(user_files) & set(sol_files)
    if common:
        summary.append(f"共同文件: ", style="dim")
        summary.append(f"{', '.join(common)}\n", style="yellow")

    # Diff sizes
    user_lines = len([l for l in user_diff.split("\n") if l.startswith("+") or l.startswith("-")])
    sol_lines = len([l for l in solution_diff.split("\n") if l.startswith("+") or l.startswith("-")])
    summary.append(f"\n你的改动行数: {user_lines}\n", style="cyan")
    summary.append(f"真实解法行数: {sol_lines}\n", style="green")

    console.print(Panel(summary, border_style="dim"))


def _extract_diff_files(diff: str) -> list[str]:
    """Extract file names from a unified diff.

    Args:
        diff: Unified diff text.

    Returns:
        List of file paths.
    """
    files = []
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            files.append(line[6:])
        elif line.startswith("--- a/"):
            fname = line[6:]
            if fname not in files:
                files.append(fname)
    return files
