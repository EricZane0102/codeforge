"""CodeForge CLI — main Typer application.

Entry point for all forge commands.
"""

from __future__ import annotations

import functools
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .config import (
    ensure_home,
    load_config,
    save_config,
    set_config_value,
    get_config_value,
    CONFIG_FILE,
    CODEFORGE_HOME,
    journal_file,
    session_file,
)
from .models import Difficulty, SessionStatus

console = Console()

app = typer.Typer(
    name="forge",
    help="🔥 CodeForge — 编码能力锻造 CLI 工具",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _error_handler(func):
    """Decorator to catch and display errors gracefully."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            console.print("\n[dim]已取消[/dim]")
            raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as e:
            console.print(f"[red]❌ 错误: {e}[/red]")
            raise SystemExit(1)
    return wrapper


# ─── Init ───────────────────────────────────────────────────────────

@app.command()
@_error_handler
def init() -> None:
    """初始化 CodeForge 工作目录 (~/.codeforge/)。"""
    home = ensure_home()

    if not CONFIG_FILE.exists():
        save_config({
            "editor": "vim",
            "api_provider": None,
            "api_key": None,
            "api_model": None,
            "time_warnings": True,
            "auto_test": True,
        })
        console.print(f"[green]✅ 配置文件已创建: {CONFIG_FILE}[/green]")
    else:
        console.print(f"[dim]配置文件已存在: {CONFIG_FILE}[/dim]")

    # Copy built-in challenges
    _install_builtin_challenges()

    console.print(Panel(
        f"[green]✅ CodeForge 已初始化！[/green]\n\n"
        f"📁 工作目录: {home}\n"
        f"📝 配置文件: {CONFIG_FILE}\n\n"
        f"[bold]下一步:[/bold]\n"
        f"  forge list       — 查看可用挑战\n"
        f"  forge challenge  — 随机获取一道题\n"
        f"  forge config     — 配置 API key 等",
        title="🔥 CodeForge",
        border_style="green",
    ))


def _install_builtin_challenges() -> None:
    """Copy built-in challenge YAML files to ~/.codeforge/challenges/."""
    import importlib.resources
    import shutil
    from pathlib import Path
    from .config import CHALLENGES_DIR

    try:
        pkg_challenges = importlib.resources.files("codeforge") / "challenges"
        pkg_path = Path(str(pkg_challenges))
        if pkg_path.exists():
            for f in pkg_path.iterdir():
                if f.suffix in (".yaml", ".yml"):
                    dest = CHALLENGES_DIR / f.name
                    if not dest.exists():
                        shutil.copy2(f, dest)
                        console.print(f"  [dim]安装挑战: {f.stem}[/dim]")
    except Exception:
        pass  # Silently skip if built-in challenges aren't available


# ─── Config ─────────────────────────────────────────────────────────

@app.command()
@_error_handler
def config(
    key: Optional[str] = typer.Argument(None, help="配置项名称"),
    value: Optional[str] = typer.Argument(None, help="要设置的值"),
) -> None:
    """查看或修改配置。

    不带参数: 显示所有配置
    带一个参数: 显示特定配置值
    带两个参数: 设置配置值

    示例:
        forge config
        forge config editor
        forge config editor nano
        forge config api_key sk-xxx
    """
    if key is None:
        # Show all config
        cfg = load_config()
        console.print(Panel(
            "\n".join(
                f"  [cyan]{k}[/cyan]: {_mask_value(k, v)}"
                for k, v in cfg.items()
            ),
            title="⚙️ 配置",
            border_style="blue",
        ))
        console.print(f"\n[dim]配置文件: {CONFIG_FILE}[/dim]")
    elif value is None:
        # Show specific value
        v = get_config_value(key)
        console.print(f"  [cyan]{key}[/cyan]: {_mask_value(key, v)}")
    else:
        # Set value
        # Convert "none" and "null" to None
        if value.lower() in ("none", "null", ""):
            value = None
        set_config_value(key, value)
        console.print(f"[green]✅ {key} = {_mask_value(key, value)}[/green]")


def _mask_value(key: str, value) -> str:
    """Mask sensitive values like API keys."""
    if value is None:
        return "[dim]未设置[/dim]"
    if "key" in key.lower() and isinstance(value, str) and len(value) > 8:
        return f"{value[:4]}...{value[-4:]}"
    return str(value)


# ─── Challenge ──────────────────────────────────────────────────────

@app.command()
@_error_handler
def challenge(
    difficulty: Optional[str] = typer.Option(
        None, "--difficulty", "-d",
        help="难度筛选: easy, medium, hard",
    ),
    id: Optional[str] = typer.Option(
        None, "--id", "-i",
        help="指定特定挑战 ID",
    ),
) -> None:
    """获取一个编码挑战。

    随机抽取一道未完成的题目，或指定难度/ID。

    示例:
        forge challenge
        forge challenge --difficulty easy
        forge challenge --id fastapi-001
    """
    from .challenge import pick_challenge
    from .workspace import display_challenge_info

    diff = None
    if difficulty:
        try:
            diff = Difficulty(difficulty.lower())
        except ValueError:
            console.print(f"[red]❌ 无效难度: {difficulty}。可选: easy, medium, hard[/red]")
            raise SystemExit(1)

    ch = pick_challenge(difficulty=diff, challenge_id=id)

    if ch is None:
        if difficulty:
            console.print(f"[yellow]没有找到 {difficulty} 难度的未完成挑战。[/yellow]")
        else:
            console.print("[yellow]🎉 所有挑战都已完成！[/yellow]")
        return

    display_challenge_info(ch)

    console.print(f"\n  运行 [bold]forge start --id {ch.id}[/bold] 开始挑战\n")


# ─── List ───────────────────────────────────────────────────────────

@app.command(name="list")
@_error_handler
def list_challenges() -> None:
    """列出所有可用挑战及其状态。"""
    from .challenge import display_challenge_list
    display_challenge_list()


# ─── Start ──────────────────────────────────────────────────────────

@app.command()
@_error_handler
def start(
    id: Optional[str] = typer.Option(
        None, "--id", "-i",
        help="挑战 ID（不指定则使用最近获取的挑战）",
    ),
) -> None:
    """开始一个挑战：下载仓库、初始化工作区、开始计时。

    示例:
        forge start --id fastapi-001
    """
    from .challenge import get_challenge, pick_challenge
    from .workspace import setup_workspace, display_challenge_info

    if id:
        ch = get_challenge(id)
        if ch is None:
            console.print(f"[red]❌ 未找到挑战: {id}[/red]")
            raise SystemExit(1)
    else:
        # Pick any incomplete challenge
        ch = pick_challenge()
        if ch is None:
            console.print("[yellow]没有可用的挑战。运行 forge list 查看全部。[/yellow]")
            return

    display_challenge_info(ch)

    console.print("\n[bold]⚙️ 初始化工作区...[/bold]\n")
    ws = setup_workspace(ch)

    console.print(Panel(
        f"[green]✅ 工作区已就绪！[/green]\n\n"
        f"📁 代码目录: {ws / 'repo'}\n"
        f"📝 思考日志: {ws / 'journal.md'}\n"
        f"⏱️  时限: {ch.time_limit} 分钟\n\n"
        f"[bold]流程:[/bold]\n"
        f"  1. [bold]forge think[/bold]       — 先写下你的分析思路\n"
        f"  2. 修改 {ws / 'repo'} 中的代码\n"
        f"  3. [bold]forge submit[/bold]      — 提交你的方案\n"
        f"  4. [bold]forge compare[/bold]     — 对比真实解法\n"
        f"  5. [bold]forge review[/bold]      — AI 评判\n\n"
        f"  💡 [bold]forge hint[/bold]        — 需要提示时使用",
        title=f"🔥 {ch.title}",
        border_style="green",
    ))


# ─── Think ──────────────────────────────────────────────────────────

@app.command()
@_error_handler
def think(
    id: Optional[str] = typer.Option(
        None, "--id", "-i",
        help="挑战 ID",
    ),
) -> None:
    """打开思考日志，记录你的分析过程。

    使用 $EDITOR 环境变量指定的编辑器（默认 vim）。
    提交前必须填写思考日志。
    """
    from .journal import open_journal

    challenge_id = id or _find_active_challenge()
    if not challenge_id:
        console.print("[red]❌ 没有进行中的挑战。请先运行 forge start。[/red]")
        return

    jf = journal_file(challenge_id)
    open_journal(jf)


# ─── Submit ─────────────────────────────────────────────────────────

@app.command()
@_error_handler
def submit(
    id: Optional[str] = typer.Option(
        None, "--id", "-i",
        help="挑战 ID",
    ),
) -> None:
    """提交你的解决方案。

    会自动：检查思考日志、保存代码改动、运行测试。
    """
    from .challenge import get_challenge
    from .submission import submit_challenge

    challenge_id = id or _find_active_challenge()
    if not challenge_id:
        console.print("[red]❌ 没有进行中的挑战。请先运行 forge start。[/red]")
        return

    ch = get_challenge(challenge_id)
    if ch is None:
        console.print(f"[red]❌ 未找到挑战: {challenge_id}[/red]")
        return

    submit_challenge(ch)


# ─── Compare ────────────────────────────────────────────────────────

@app.command()
@_error_handler
def compare(
    id: Optional[str] = typer.Option(
        None, "--id", "-i",
        help="挑战 ID",
    ),
    side_by_side: bool = typer.Option(
        False, "--side-by-side", "-s",
        help="并排显示",
    ),
) -> None:
    """对比你的方案与真实解法。"""
    from .challenge import get_challenge
    from .compare import compare_solutions

    challenge_id = id or _find_submitted_challenge()
    if not challenge_id:
        console.print("[red]❌ 没有已提交的挑战。请先运行 forge submit。[/red]")
        return

    ch = get_challenge(challenge_id)
    if ch is None:
        console.print(f"[red]❌ 未找到挑战: {challenge_id}[/red]")
        return

    compare_solutions(ch, side_by_side=side_by_side)


# ─── Review ─────────────────────────────────────────────────────────

@app.command()
@_error_handler
def review(
    id: Optional[str] = typer.Option(
        None, "--id", "-i",
        help="挑战 ID",
    ),
    export: bool = typer.Option(
        False, "--export", "-e",
        help="强制使用导出模式（不调用 API）",
    ),
    score: bool = typer.Option(
        False, "--score",
        help="手动录入评分",
    ),
) -> None:
    """AI 评判你的解决方案。

    API 模式（配了 key）自动评分，否则生成导出文本供手动评判。
    """
    from .challenge import get_challenge
    from .review import review_challenge, save_manual_review

    challenge_id = id or _find_submitted_challenge()
    if not challenge_id:
        console.print("[red]❌ 没有已提交的挑战。请先运行 forge submit。[/red]")
        return

    if score:
        # Manual score entry
        console.print("[bold]手动录入评分[/bold]\n")
        correctness = typer.prompt("Correctness (1-10)", type=int)
        approach = typer.prompt("Approach (1-10)", type=int)
        code_quality = typer.prompt("Code Quality (1-10)", type=int)
        edge_cases = typer.prompt("Edge Cases (1-10)", type=int)
        thinking = typer.prompt("Thinking Quality (1-10)", type=int)
        feedback = typer.prompt("反馈 (可选)", default="")

        save_manual_review(
            challenge_id,
            correctness=correctness,
            approach=approach,
            code_quality=code_quality,
            edge_cases=edge_cases,
            thinking_quality=thinking,
            feedback=feedback,
        )
        return

    ch = get_challenge(challenge_id)
    if ch is None:
        console.print(f"[red]❌ 未找到挑战: {challenge_id}[/red]")
        return

    review_challenge(ch, export=export)


# ─── Hint ───────────────────────────────────────────────────────────

@app.command()
@_error_handler
def hint(
    id: Optional[str] = typer.Option(
        None, "--id", "-i",
        help="挑战 ID",
    ),
) -> None:
    """获取提示（每使用一个提示会影响评分 -0.5分）。"""
    from .challenge import get_challenge
    from .hints import show_hint

    challenge_id = id or _find_active_challenge()
    if not challenge_id:
        console.print("[red]❌ 没有进行中的挑战。请先运行 forge start。[/red]")
        return

    ch = get_challenge(challenge_id)
    if ch is None:
        console.print(f"[red]❌ 未找到挑战: {challenge_id}[/red]")
        return

    show_hint(ch)


# ─── Stats ──────────────────────────────────────────────────────────

@app.command()
@_error_handler
def stats(
    last: Optional[int] = typer.Option(
        None, "--last", "-n",
        help="只显示最近 N 次挑战",
    ),
) -> None:
    """查看你的统计数据和进度。"""
    from .stats import display_stats
    display_stats(last_n=last)


# ─── Version ────────────────────────────────────────────────────────

@app.command()
def version() -> None:
    """显示版本信息。"""
    console.print(f"🔥 CodeForge v{__version__}")


# ─── Reset ──────────────────────────────────────────────────────────

@app.command()
@_error_handler
def reset(
    id: str = typer.Option(..., "--id", "-i", help="挑战 ID"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """重置一个挑战（删除工作区和记录）。"""
    import shutil
    from .config import workspace_path

    ws = workspace_path(id)
    if not ws.exists():
        console.print(f"[yellow]挑战 {id} 没有工作区。[/yellow]")
        return

    if not confirm:
        if not typer.confirm(f"确定要重置挑战 {id}？这会删除所有工作数据。"):
            console.print("[dim]已取消[/dim]")
            return

    shutil.rmtree(ws)
    console.print(f"[green]✅ 挑战 {id} 已重置。[/green]")


# ─── Helpers ────────────────────────────────────────────────────────

def _find_active_challenge() -> Optional[str]:
    """Find the most recent active (in-progress) challenge.

    Returns:
        Challenge ID or None.
    """
    from .challenge import load_all_challenges
    from .models import Session

    challenges = load_all_challenges()
    active = []

    for ch in challenges:
        sf = session_file(ch.id)
        if sf.exists():
            try:
                session = Session.load(sf)
                if session.status == SessionStatus.IN_PROGRESS and session.start_time:
                    active.append((ch.id, session.start_time))
            except Exception:
                continue

    if not active:
        return None

    # Return the most recently started
    active.sort(key=lambda x: x[1], reverse=True)
    return active[0][0]


def _find_submitted_challenge() -> Optional[str]:
    """Find the most recent submitted or reviewed challenge.

    Returns:
        Challenge ID or None.
    """
    from .challenge import load_all_challenges
    from .models import Session

    challenges = load_all_challenges()
    submitted = []

    for ch in challenges:
        sf = session_file(ch.id)
        if sf.exists():
            try:
                session = Session.load(sf)
                if session.status in (SessionStatus.SUBMITTED, SessionStatus.REVIEWED):
                    submitted.append((ch.id, session.end_time or session.start_time or ""))
            except Exception:
                continue

    if not submitted:
        return None

    submitted.sort(key=lambda x: x[1], reverse=True)
    return submitted[0][0]


if __name__ == "__main__":
    app()
