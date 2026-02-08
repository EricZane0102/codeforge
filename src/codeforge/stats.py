"""Statistics tracking for CodeForge.

Tracks challenge history, scores, and displays progress
visualizations using Rich in the terminal.

Includes: radar chart, growth curve, and level system.
"""

from __future__ import annotations

import json
import math
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

# ─── Level System ──────────────────────────────────────────────────

LEVELS = [
    {
        "level": 1,
        "title": "Novice",
        "title_cn": "新手",
        "min_completed": 1,
        "min_avg_score": 0,
        "min_hard": 0,
        "icon": "🌱",
    },
    {
        "level": 2,
        "title": "Apprentice",
        "title_cn": "学徒",
        "min_completed": 5,
        "min_avg_score": 5,
        "min_hard": 0,
        "icon": "🔧",
    },
    {
        "level": 3,
        "title": "Journeyman",
        "title_cn": "熟手",
        "min_completed": 10,
        "min_avg_score": 6,
        "min_hard": 0,
        "icon": "⚔️",
    },
    {
        "level": 4,
        "title": "Craftsman",
        "title_cn": "匠人",
        "min_completed": 15,
        "min_avg_score": 7,
        "min_hard": 1,
        "icon": "🛡️",
    },
    {
        "level": 5,
        "title": "Master",
        "title_cn": "大师",
        "min_completed": 18,
        "min_avg_score": 8,
        "min_hard": 3,
        "icon": "👑",
    },
]


def calculate_level(stats: list[dict]) -> dict:
    """Calculate the user's current level based on performance.

    Returns:
        The level dict the user has achieved.
    """
    reviewed = [s for s in stats if "average_score" in s]
    completed = len(stats)
    avg_score = sum(s["average_score"] for s in reviewed) / len(reviewed) if reviewed else 0
    hard_completed = sum(1 for s in reviewed if s["difficulty"] == "hard")

    current_level = LEVELS[0]
    for level in LEVELS:
        if (completed >= level["min_completed"]
                and avg_score >= level["min_avg_score"]
                and hard_completed >= level["min_hard"]):
            current_level = level
        else:
            break

    return current_level


def check_level_up(old_stats: list[dict], new_stats: list[dict]) -> Optional[dict]:
    """Check if the user leveled up after a new review.

    Returns:
        The new level dict if leveled up, None otherwise.
    """
    old_level = calculate_level(old_stats)
    new_level = calculate_level(new_stats)
    if new_level["level"] > old_level["level"]:
        return new_level
    return None


def display_level_up(level: dict) -> None:
    """Display a level-up celebration message."""
    console.print()
    console.print(Panel(
        f"[bold yellow]{level['icon']}  恭喜！你升级了！[/bold yellow]\n\n"
        f"  [bold]Lv.{level['level']} {level['title']} ({level['title_cn']})[/bold]",
        title="[bold]🎉 升级[/bold]",
        border_style="yellow",
    ))


# ─── Data Collection ───────────────────────────────────────────────

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


# ─── Main Display ──────────────────────────────────────────────────

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

    # Level + Overall summary
    _display_level_and_summary(all_stats)

    # Score chart + radar
    reviewed = [s for s in all_stats if "review" in s]
    if reviewed:
        _display_radar_chart(reviewed)
        _display_growth_curve(reviewed)
        _display_dimension_breakdown(reviewed)

    # Difficulty breakdown
    _display_difficulty_stats(all_stats)

    # Recent challenges table
    _display_recent_table(display_stats_list)


# ─── Level + Summary ──────────────────────────────────────────────

def _display_level_and_summary(stats: list[dict]) -> None:
    """Display level badge and overall summary."""
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

    # Calculate level
    level = calculate_level(stats)

    # Next level info
    next_level = None
    for lv in LEVELS:
        if lv["level"] == level["level"] + 1:
            next_level = lv
            break

    summary = Text()

    # Level badge
    summary.append(f"  {level['icon']}  ", style="bold")
    summary.append(f"Lv.{level['level']} {level['title']}", style="bold cyan")
    summary.append(f" ({level['title_cn']})", style="cyan")

    if next_level:
        summary.append(f"  →  下一级: Lv.{next_level['level']} {next_level['title']}", style="dim")
        # Show what's needed
        needs = []
        if total < next_level["min_completed"]:
            needs.append(f"完成 {next_level['min_completed']} 题")
        if avg_score < next_level["min_avg_score"]:
            needs.append(f"均分 ≥ {next_level['min_avg_score']}")
        if next_level["min_hard"] > 0:
            hard_done = sum(1 for s in reviewed if s["difficulty"] == "hard")
            if hard_done < next_level["min_hard"]:
                needs.append(f"完成 {next_level['min_hard']} 个 hard")
        if needs:
            summary.append(f" (需要: {', '.join(needs)})", style="dim")

    summary.append("\n\n")
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

    console.print(Panel(summary, title="[bold]📊 CodeForge 总览[/bold]", border_style="cyan"))


# ─── Radar Chart ───────────────────────────────────────────────────

def _display_radar_chart(reviewed: list[dict]) -> None:
    """Display a text-based radar chart of 5 dimensions."""
    dimensions = ["correctness", "approach", "code_quality", "edge_cases", "thinking_quality"]
    dim_labels = ["正确性", "方法", "代码质量", "边界", "思考"]

    # Calculate averages
    avgs = {}
    for dim in dimensions:
        scores = [s["review"].get(dim, 0) for s in reviewed if "review" in s]
        avgs[dim] = sum(scores) / len(scores) if scores else 0

    # Find weakest dimension
    weakest_dim = min(avgs, key=avgs.get)
    weakest_label = dim_labels[dimensions.index(weakest_dim)]
    weakest_val = avgs[weakest_dim]

    # Build radar visualization
    # Using a simplified 5-point star layout in text
    # Layout: top (correctness), upper-right (approach), lower-right (code_quality),
    #          lower-left (edge_cases), upper-left (thinking_quality)

    vals = [avgs[d] for d in dimensions]
    # Scale values to 0-5 for drawing (map 0-10 to 0-5 steps)
    scaled = [min(5, int(v / 2 + 0.5)) for v in vals]

    # Render a compact radar using Rich Text
    radar = Text()

    # Row by row text radar (11 rows, center at row 5)
    # Each dimension extends in a direction from center
    # Top: correctness (up), upper-right: approach, lower-right: code_quality
    # lower-left: edge_cases, upper-left: thinking_quality

    # Simpler approach: show as a pentagonal profile with bars
    radar.append("  能力雷达\n\n", style="bold")

    for i, dim in enumerate(dimensions):
        val = avgs[dim]
        label = dim_labels[i]
        filled = int(val)
        half = val - filled
        bar = "██" * filled
        if half >= 0.5:
            bar += "▌"
        empty_width = 20 - len(bar)
        empty = "░░" * max(0, (10 - filled))
        if half >= 0.5:
            empty = "░" * max(0, (20 - len(bar) - 1)) if len(bar) < 20 else ""
        else:
            empty = "░" * max(0, (20 - len(bar)))

        color = "green" if val >= 7 else "yellow" if val >= 5 else "red"
        padded_label = f"  {label}".ljust(10)

        radar.append(padded_label, style="dim")
        radar.append(f" [{color}]{bar}{empty}[/{color}] ")
        radar.append(f"{val:.1f}\n", style=f"bold {color}")

    # Weakness callout
    radar.append(f"\n  [bold yellow]短板:[/bold yellow] {weakest_label} ({weakest_val:.1f})")
    weak_color = "red" if weakest_val < 5 else "yellow"
    radar.append(f"  [{weak_color}]建议多练相关类型的挑战[/{weak_color}]")

    console.print()
    console.print(Panel(radar, title="[bold]🎯 能力雷达[/bold]", border_style="magenta"))


# ─── Growth Curve ──────────────────────────────────────────────────

def _display_growth_curve(reviewed: list[dict]) -> None:
    """Display a text-based growth curve showing score trends."""
    if len(reviewed) < 2:
        return

    # Chronological order (oldest first)
    display = list(reversed(reviewed[:15]))

    scores = [s["average_score"] for s in display]

    # Chart dimensions
    chart_height = 8
    chart_width = min(len(scores) * 4, 60)

    # Scale: 0-10 mapped to 0-chart_height
    max_score = 10
    min_score = 0

    console.print()

    chart = Text()
    chart.append("  成长曲线\n\n", style="bold")

    # Draw chart row by row (top to bottom)
    for row in range(chart_height, -1, -1):
        threshold = min_score + (max_score - min_score) * row / chart_height

        # Y-axis label
        if row == chart_height:
            chart.append("  10│", style="dim")
        elif row == chart_height // 2:
            chart.append("   5│", style="dim")
        elif row == 0:
            chart.append("   0│", style="dim")
        else:
            chart.append("    │", style="dim")

        # Plot points
        for i, score in enumerate(scores):
            score_row = int(score / max_score * chart_height + 0.5)
            if score_row == row:
                color = "green" if score >= 7 else "yellow" if score >= 5 else "red"
                chart.append(f" [{color}]●[/{color}] ")
            elif score_row > row:
                # Below the point - draw vertical line for connection
                if i > 0:
                    prev_row = int(scores[i-1] / max_score * chart_height + 0.5)
                    curr_row = score_row
                    if min(prev_row, curr_row) <= row <= max(prev_row, curr_row):
                        chart.append(" [dim]·[/dim] ")
                    else:
                        chart.append("    ")
                else:
                    chart.append("    ")
            else:
                chart.append("    ")

        chart.append("\n")

    # X-axis
    chart.append("    └", style="dim")
    for i in range(len(scores)):
        chart.append("────", style="dim")
    chart.append("\n")

    # X labels (challenge numbers)
    chart.append("     ", style="dim")
    for i in range(len(scores)):
        chart.append(f" #{i+1} ", style="dim")

    # Trend indicator
    if len(scores) >= 3:
        recent_avg = sum(scores[-3:]) / 3
        early_avg = sum(scores[:3]) / 3
        diff = recent_avg - early_avg
        if diff > 0.5:
            chart.append(f"\n\n  [green]↗ 上升趋势 (+{diff:.1f})[/green]")
        elif diff < -0.5:
            chart.append(f"\n\n  [red]↘ 下降趋势 ({diff:.1f})[/red]")
        else:
            chart.append(f"\n\n  [yellow]→ 稳定 ({diff:+.1f})[/yellow]")

    console.print(Panel(chart, title="[bold]📈 成长曲线[/bold]", border_style="green"))


# ─── Dimension Breakdown ──────────────────────────────────────────

def _display_dimension_breakdown(reviewed: list[dict]) -> None:
    """Display average scores per dimension."""
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

    console.print()
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


# ─── Difficulty Stats ─────────────────────────────────────────────

def _display_difficulty_stats(stats: list[dict]) -> None:
    """Display statistics grouped by difficulty."""
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


# ─── Recent Table ─────────────────────────────────────────────────

def _display_recent_table(stats: list[dict]) -> None:
    """Display a table of recent challenge attempts."""
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
