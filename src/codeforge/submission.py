"""Submission system for CodeForge.

Handles submitting a challenge attempt: validates journal,
captures git diff, runs tests, and updates session state.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from .config import (
    journal_file,
    session_file,
    submission_dir,
    workspace_path,
)
from .git_ops import get_all_changes, has_changes
from .journal import validate_journal
from .models import Challenge, Session, SessionStatus

console = Console()


def submit_challenge(challenge: Challenge) -> bool:
    """Submit the current challenge attempt.

    Steps:
    1. Validate journal is filled
    2. Check for code changes
    3. Save git diff to submission/
    4. Run tests if configured
    5. Update session state

    Args:
        challenge: The challenge being submitted.

    Returns:
        True if submission succeeded, False otherwise.
    """
    sf = session_file(challenge.id)
    jf = journal_file(challenge.id)
    ws = workspace_path(challenge.id)
    repo_dir = ws / "repo"
    sub_dir = submission_dir(challenge.id)

    # Load session
    if not sf.exists():
        console.print("[red]❌ 没有找到进行中的会话。请先运行 forge start。[/red]")
        return False

    session = Session.load(sf)

    if session.status == SessionStatus.SUBMITTED:
        console.print("[yellow]⚠ 此挑战已经提交过了。[/yellow]")
        return False

    if session.status == SessionStatus.REVIEWED:
        console.print("[yellow]⚠ 此挑战已经评判过了。[/yellow]")
        return False

    if session.status != SessionStatus.IN_PROGRESS:
        console.print("[red]❌ 会话状态异常。请先运行 forge start。[/red]")
        return False

    # Validate journal
    valid, reason = validate_journal(jf)
    if not valid:
        console.print(f"[red]❌ 思考日志校验未通过：[/red]\n{reason}")
        return False

    # Check for changes
    if not has_changes(repo_dir):
        console.print("[red]❌ 没有检测到代码改动。请先修改代码再提交。[/red]")
        return False

    # Capture diff
    user_diff = get_all_changes(repo_dir)
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "user.diff").write_text(user_diff, encoding="utf-8")
    session.user_diff = user_diff

    # Run tests if configured
    if challenge.setup.test_command:
        console.print("[bold]🧪 运行测试...[/bold]")
        test_passed, test_output = _run_tests(
            repo_dir, challenge.setup.test_command
        )
        session.test_passed = test_passed
        session.test_output = test_output

        if test_passed:
            console.print("[green]✅ 测试通过！[/green]")
        else:
            console.print("[red]❌ 测试未通过。[/red]")
            console.print(Panel(test_output[:2000], title="测试输出", border_style="red"))

    # Update session
    session.submit()
    session.save(sf)

    # Show summary
    elapsed = session.elapsed_minutes
    time_str = f"{elapsed:.1f} 分钟" if elapsed else "未知"
    hints_str = f"{len(session.hints_used)} 个" if session.hints_used else "无"

    console.print()
    console.print(Panel(
        f"[green]✅ 提交成功！[/green]\n\n"
        f"⏱️  用时: {time_str}\n"
        f"💡 使用提示: {hints_str}\n"
        f"🧪 测试: {'通过' if session.test_passed else '未通过' if session.test_passed is not None else '未配置'}\n\n"
        f"[dim]下一步:[/dim]\n"
        f"  forge compare  — 查看你的方案 vs 真实解法\n"
        f"  forge review   — AI 评判",
        title="📝 提交摘要",
        border_style="green",
    ))

    return True


def _run_tests(
    repo_dir: Path, test_command: str, timeout: int = 120
) -> tuple[bool, str]:
    """Run the test command in the repo directory.

    Args:
        repo_dir: Path to the repository.
        test_command: Shell command to run tests.
        timeout: Test timeout in seconds.

    Returns:
        Tuple of (passed, output).
    """
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + "\n" + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"测试超时 ({timeout}s)"
    except Exception as e:
        return False, f"测试运行失败: {e}"
