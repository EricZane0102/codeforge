"""Statistics tracking for CodeForge.

Tracks challenge history, scores, and displays progress
visualizations using Rich in the terminal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import HISTORY_FILE, WORKSPACES_DIR, session_file
from .models import (
    Challenge,
    Difficulty,
    ReviewScore,
    Session,
    SessionStatus,
)
from .challenge import load_all_challenges, get_session_status

console = Console()


def collect_stats() -> list[dict]:
    """Collect statistics from all completed sessions.

    Returns:
        List of session summary dicts.
    """
    stats = []
    challenges = load_all_challenges()

    for challenge in challenges:
        sf = session_file(challenge.id)
        if not sf.exists():
            continue

        try:
            session = Session.load(sf)
        except Exception:
            continue

        if session.status not in (SessionStatus.SUBMITTED, SessionStatus.REVIEWED):
            continue

        entry = {
            "id": challenge.id,
            "title": challenge.title,
            "difficulty": challenge.difficulty.value,
            "status": session.status.value,
            "elapsed_minutes": session.elapsed_minutes,
            "hints_used": len(session.hints_used),
            "test_passed": session.test_passed,
            "start_time": session.start_time,
            "end_time": session.end_time,
        }

        if session.review:
            entry["review"] = session.review.to_dict()
            entry["average_score"] = session.review.average

        stats.append(entry)

    return stats


def display_stats(last_n: Optional[int] = None) -> None:
    """Display comprehensive statistics.

    Args:
        last_n: Only show the last N challenges.
    """
    all_stats = collect_stats()

    if not all_stats:
        console.print("[yellow]还没有完成任何挑战。开始你的第一个挑战吧！[/yellow]")
        console.print("运行 [bold]forge challenge[/bold] 获取一道题目")
        return

    # Sort by start time (most recent first)
    all_stats.sort(key=lambda x: x.get("start_time", ""), reverse=True)

    if last_n:
        display_stats_list = all_stats[:last_n]
    else:
        display_stats_list = all_stats

    # Overall summary
    _display_summary(all_stats)

    # Score chart
    reviewed = [s for s in all_stats if "review" in s]
    if reviewed:
        _display_score_chart(reviewed)
        _display_dimension_breakdown(reviewed)

    # Difficulty breakdown
    _display_difficulty_stats(all_stats)

    # Recent challenges table
    _display_recent_table(display_stats_list)


def _display_summary(stats: list[dict]) -> None:
    """Display overall summary statistics.

    Args:
        stats: List of session stats.
    """
    total = len(stats)
    reviewed = [s for s in stats if "review" in s]
    passed = sum(1 for s in stats if s.get("test_passed"))

    avg_score = 0.0
    if reviewed:
        avg_score = sum(s["average_score"] for s in reviewed) / len(reviewed)

    avg_time = 0.0
    timed = [s for s in stats if s.get("elapsed_minutes")]
    if timed:
        avg_time = sum(s["elapsed_minutes"] for s in timed) / len(timed)

    total_hints = sum(s.get("hints_used", 0) for s in stats)

    summary = Text()
    summary.append("📊 总览\n\n", style="bold")
    summary.append(f"  完成挑战: ", style="dim")
    summary.append(f"{total}\n", style="bold cyan")
    summary.append(f"  已评判:   ", style="dim")
    summary.append(f"{len(reviewed)}\n", style="bold")
    summary.append(f"  测试通过: ", style="dim")
    summary.append(f"{passed}/{total}\n", style="bold green" if passed == total else "bold yellow")
    summary.append(f"  平均评分: ", style="dim")
    summary.append(f"{avg_score:.1f}/10\n", style=_score_color(avg_score))
    summary.append(f"  平均用时: ", style="dim")
    summary.append(f"{avg_time:.1f} 分钟\n", style="bold")
    summary.append(f"  总提示数: ", style="dim")
    summary.append(f"{total_hints}\n", style="bold yellow" if total_hints > 0 else "bold green")

    console.print(Panel(summary, border_style="cyan"))


def _display_score_chart(reviewed: list[dict]) -> None:
    """Display a bar chart of scores over time.

    Args:
        reviewed: List of reviewed stats.
    """
    console.print()
    console.print("[bold]📈 评分趋势[/bold]\n")

    # Show most recent first (reversed for chronological display)
    display = list(reversed(reviewed[:10]))

    for s in display:
        score = s["average_score"]
        bar_width = int(score * 3)  # Scale to ~30 chars max
        bar = "█" * bar_width
        color = "green" if score >= 7 else "yellow" if score >= 5 else "red"

        label = s["id"][:20].ljust(20)
        console.print(
            f"  {label} [{color}]{bar}[/{color}] {score:.1f}"
        )

    console.print()


def _display_dimension_breakdown(reviewed: list[dict]) -> None:
    """Display average scores per dimension.

    Args:
        reviewed: List of reviewed stats.
    """
    if not reviewed:
        return

    dimensions = ["correctness", "approach", "code_quality", "edge_cases", "thinking_quality"]
    dim_names = {
        "correctness": "🎯 Correctness",
        "approach": "🧭 Approach",
        "code_quality": "✨ Code Quality",
        "edge_cases": "🔍 Edge Cases",
        "thinking_quality": "🧠 Thinking",
    }

    console.print("[bold]📊 维度平均分[/bold]\n")

    for dim in dimensions:
        scores = [s["review"].get(dim, 0) for s in reviewed if "review" in s]
        if scores:
            avg = sum(scores) / len(scores)
            bar_width = int(avg * 3)
            bar = "█" * bar_width
            empty = "░" * (30 - bar_width)
            color = "green" if avg >= 7 else "yellow" if avg >= 5 else "red"

            name = dim_names.get(dim, dim).ljust(22)
            console.print(
                f"  {name} [{color}]{bar}{empty}[/{color}] {avg:.1f}"
            )

    console.print()


def _display_difficulty_stats(stats: list[dict]) -> None:
    """Display statistics grouped by difficulty.

    Args:
        stats: List of session stats.
    """
    table = Table(title="🎯 按难度统计", show_lines=True)
    table.add_column("难度", min_width=10)
    table.add_column("完成数", justify="center")
    table.add_column("平均分", justify="center")
    table.add_column("平均用时", justify="center")
    table.add_column("通过率", justify="center")

    for diff in [Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD]:
        diff_stats = [s for s in stats if s["difficulty"] == diff.value]
        if not diff_stats:
            continue

        count = len(diff_stats)
        reviewed = [s for s in diff_stats if "average_score" in s]
        avg_score = sum(s["average_score"] for s in reviewed) / len(reviewed) if reviewed else 0

        timed = [s for s in diff_stats if s.get("elapsed_minutes")]
        avg_time = sum(s["elapsed_minutes"] for s in timed) / len(timed) if timed else 0

        passed = sum(1 for s in diff_stats if s.get("test_passed"))
        pass_rate = f"{passed}/{count}"

        color = {"easy": "green", "medium": "yellow", "hard": "red"}.get(diff.value, "white")
        table.add_row(
            f"[{color}]{diff.value}[/{color}]",
            str(count),
            f"{avg_score:.1f}" if reviewed else "—",
            f"{avg_time:.0f}min" if timed else "—",
            pass_rate,
        )

    console.print(table)
    console.print()


def _display_recent_table(stats: list[dict]) -> None:
    """Display a table of recent challenge attempts.

    Args:
        stats: List of session stats (already sorted).
    """
    table = Table(title="📋 最近挑战", show_lines=True)
    table.add_column("ID", style="cyan", min_width=15)
    table.add_column("难度", min_width=8)
    table.add_column("用时", justify="right")
    table.add_column("提示", justify="center")
    table.add_column("测试", justify="center")
    table.add_column("评分", justify="center")
    table.add_column("状态", min_width=8)

    for s in stats[:15]:
        diff_color = {"easy": "green", "medium": "yellow", "hard": "red"}.get(
            s["difficulty"], "white"
        )
        elapsed = f"{s['elapsed_minutes']:.0f}min" if s.get("elapsed_minutes") else "—"
        hints = str(s.get("hints_used", 0))
        test = "✅" if s.get("test_passed") else ("❌" if s.get("test_passed") is False else "—")
        score = f"{s['average_score']:.1f}" if "average_score" in s else "—"
        status = "⭐" if s["status"] == "reviewed" else "✅"

        table.add_row(
            s["id"],
            f"[{diff_color}]{s['difficulty']}[/{diff_color}]",
            elapsed,
            hints,
            test,
            score,
            status,
        )

    console.print(table)


def _score_color(score: float) -> str:
    """Get the color style for a score value."""
    if score >= 7:
        return "bold green"
    elif score >= 5:
        return "bold yellow"
    else:
        return "bold red"
