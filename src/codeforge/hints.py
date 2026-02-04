"""Hint system for CodeForge.

Manages progressive hints for challenges. Each hint used
is recorded in the session and affects the final review score.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from .config import session_file
from .models import Challenge, Session, SessionStatus

console = Console()


def show_hint(challenge: Challenge) -> bool:
    """Show the next available hint for a challenge.

    Hints are revealed progressively. Each hint used is recorded
    in the session and will affect the review score.

    Args:
        challenge: The challenge to get a hint for.

    Returns:
        True if a hint was shown.
    """
    sf = session_file(challenge.id)

    if not sf.exists():
        console.print("[red]❌ 没有进行中的会话。请先运行 forge start。[/red]")
        return False

    session = Session.load(sf)

    if session.status != SessionStatus.IN_PROGRESS:
        console.print("[yellow]⚠ 此挑战不在进行中。[/yellow]")
        return False

    total_hints = len(challenge.hints)
    if total_hints == 0:
        console.print("[yellow]⚠ 此挑战没有可用提示。[/yellow]")
        return False

    used_count = len(session.hints_used)

    if used_count >= total_hints:
        console.print("[yellow]⚠ 所有提示已用完。[/yellow]")
        _show_all_used_hints(challenge, session)
        return False

    # Reveal next hint
    next_idx = used_count
    session.hints_used.append(next_idx)
    session.save(sf)

    hint_text = challenge.hints[next_idx]

    console.print()
    console.print(Panel(
        f"[bold]{hint_text}[/bold]",
        title=f"[yellow]💡 提示 {next_idx + 1}/{total_hints}[/yellow]",
        subtitle=f"[dim]⚠ 使用提示会影响最终评分（-0.5分/个）[/dim]",
        border_style="yellow",
    ))

    remaining = total_hints - next_idx - 1
    if remaining > 0:
        console.print(f"  [dim]还剩 {remaining} 个提示可用[/dim]")
    else:
        console.print("  [dim]这是最后一个提示了[/dim]")

    return True


def _show_all_used_hints(challenge: Challenge, session: Session) -> None:
    """Show all previously used hints.

    Args:
        challenge: The challenge.
        session: The session data.
    """
    console.print("\n[dim]已使用的提示：[/dim]")
    for i in session.hints_used:
        if i < len(challenge.hints):
            console.print(f"  💡 {i + 1}. {challenge.hints[i]}")


def show_hint_status(challenge: Challenge) -> None:
    """Show the current hint usage status.

    Args:
        challenge: The challenge.
    """
    sf = session_file(challenge.id)
    total = len(challenge.hints)

    if not sf.exists():
        console.print(f"  💡 提示: {total} 个可用")
        return

    session = Session.load(sf)
    used = len(session.hints_used)

    console.print(f"  💡 提示: {used}/{total} 已使用")
    if used > 0:
        penalty = used * 0.5
        console.print(f"  [yellow]⚠ 当前惩罚: -{penalty:.1f} 分[/yellow]")
