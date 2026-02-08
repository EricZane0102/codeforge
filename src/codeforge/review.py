"""Review / judge engine for CodeForge.

Supports two modes:
- API mode: Uses Anthropic or OpenAI API for automated 5-dimension scoring
- Export mode: Generates formatted text for manual AI evaluation
"""

from __future__ import annotations

import json
import re
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import (
    load_config,
    session_file,
    journal_file,
    workspace_path,
)
from .journal import read_journal
from .models import Challenge, Session, SessionStatus, ReviewScore

console = Console()

REVIEW_PROMPT = """你是一位资深代码评审专家。请根据以下信息对编码练习进行五维度评分。

## 挑战描述
{description}

## 用户的思考日志
```
{journal}
```

## 用户的代码改动 (diff)
```diff
{user_diff}
```

## 真实解法 (diff)
```diff
{solution_diff}
```

## 评分维度（每项 1-10 分）
1. **Correctness**: 代码是否正确解决了问题？
2. **Approach**: 解题思路与真实方案的契合度如何？
3. **Code Quality**: 代码风格、可读性、Pythonic 程度
4. **Edge Cases**: 是否考虑了边界情况？
5. **Thinking Quality**: 思考日志的深度和准确性

## 用户使用了 {hints_used} 个提示（共 {total_hints} 个可用）

请严格按照以下 JSON 格式返回评分（不要返回其他内容）：
```json
{{
    "correctness": <1-10>,
    "approach": <1-10>,
    "code_quality": <1-10>,
    "edge_cases": <1-10>,
    "thinking_quality": <1-10>,
    "feedback": "<综合评价，200字以内>"
}}
```"""


def review_challenge(challenge: Challenge, export: bool = False) -> bool:
    """Review a submitted challenge.

    Args:
        challenge: The challenge to review.
        export: Force export mode even if API key is configured.

    Returns:
        True if review succeeded.
    """
    sf = session_file(challenge.id)
    jf = journal_file(challenge.id)

    if not sf.exists():
        console.print("[red]❌ 没有找到会话记录。请先完成并提交挑战。[/red]")
        return False

    session = Session.load(sf)

    if session.status not in (SessionStatus.SUBMITTED, SessionStatus.REVIEWED):
        console.print("[red]❌ 请先提交你的方案（forge submit）再评判。[/red]")
        return False

    # Read journal
    journal_content = read_journal(jf)

    # Build the review context
    config = load_config()
    api_key = config.get("api_key")
    api_provider = config.get("api_provider")

    if not export and api_key and api_provider:
        # API mode
        score = _api_review(
            challenge=challenge,
            session=session,
            journal=journal_content,
            provider=api_provider,
            api_key=api_key,
            model=config.get("api_model"),
        )
        if score:
            # Apply hint penalty
            score = _apply_hint_penalty(score, session, challenge)

            # Collect stats before this review for level-up check
            from .stats import collect_stats
            old_stats = collect_stats()

            session.review = score
            session.status = SessionStatus.REVIEWED
            session.save(sf)
            _display_review(score, challenge, session)

            # Check for level-up
            from .stats import collect_stats as collect_new, check_level_up, display_level_up
            new_stats = collect_new()
            level_up = check_level_up(old_stats, new_stats)
            if level_up:
                display_level_up(level_up)

            return True
        else:
            console.print("[yellow]⚠ API 评判失败，切换到导出模式。[/yellow]")

    # Export mode
    _export_review(challenge, session, journal_content)
    return True


def _api_review(
    challenge: Challenge,
    session: Session,
    journal: str,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
) -> Optional[ReviewScore]:
    """Call AI API for automated review.

    Args:
        challenge: The challenge.
        session: The session data.
        journal: Journal content.
        provider: API provider ("anthropic", "openai", or "openrouter").
        api_key: API key.
        model: Model name (optional).

    Returns:
        ReviewScore if successful, None if failed.
    """
    prompt = REVIEW_PROMPT.format(
        description=challenge.description,
        journal=journal[:3000],  # Truncate
        user_diff=session.user_diff[:5000],
        solution_diff=session.solution_diff[:5000],
        hints_used=len(session.hints_used),
        total_hints=len(challenge.hints),
    )

    try:
        import httpx

        if provider == "anthropic":
            return _call_anthropic(prompt, api_key, model or "claude-sonnet-4-20250514")
        elif provider == "openai":
            return _call_openai(prompt, api_key, model or "gpt-4o")
        elif provider == "openrouter":
            return _call_openrouter(prompt, api_key, model or "anthropic/claude-sonnet-4")
        else:
            console.print(f"[red]❌ 不支持的 API 提供商: {provider}。支持: anthropic, openai, openrouter[/red]")
            return None
    except ImportError:
        console.print("[red]❌ httpx 未安装。[/red]")
        return None
    except Exception as e:
        console.print(f"[red]❌ API 调用失败: {e}[/red]")
        return None


def _call_anthropic(prompt: str, api_key: str, model: str) -> Optional[ReviewScore]:
    """Call Anthropic API for review.

    Args:
        prompt: The review prompt.
        api_key: Anthropic API key.
        model: Model name.

    Returns:
        ReviewScore if successful.
    """
    import httpx

    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    text = data["content"][0]["text"]
    return _parse_review_json(text)


def _call_openai(prompt: str, api_key: str, model: str) -> Optional[ReviewScore]:
    """Call OpenAI API for review.

    Args:
        prompt: The review prompt.
        api_key: OpenAI API key.
        model: Model name.

    Returns:
        ReviewScore if successful.
    """
    import httpx

    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    return _parse_review_json(text)


def _call_openrouter(prompt: str, api_key: str, model: str) -> Optional[ReviewScore]:
    """Call OpenRouter API for review.

    OpenRouter provides unified access to multiple LLM providers.
    Uses OpenAI-compatible API format.

    Args:
        prompt: The review prompt.
        api_key: OpenRouter API key.
        model: Model name (e.g. "anthropic/claude-sonnet-4", "openai/gpt-4o").

    Returns:
        ReviewScore if successful.
    """
    import httpx

    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/EricZane0102/codeforge",
            "X-Title": "CodeForge",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    return _parse_review_json(text)


def _parse_review_json(text: str) -> Optional[ReviewScore]:
    """Parse review JSON from AI response.

    Args:
        text: The AI response text.

    Returns:
        ReviewScore if parsing succeeded.
    """
    # Try to extract JSON from the response
    json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if not json_match:
        console.print("[yellow]⚠ 无法从 AI 响应中提取 JSON。[/yellow]")
        return None

    try:
        data = json.loads(json_match.group())
        return ReviewScore(
            correctness=_clamp(data.get("correctness", 0)),
            approach=_clamp(data.get("approach", 0)),
            code_quality=_clamp(data.get("code_quality", 0)),
            edge_cases=_clamp(data.get("edge_cases", 0)),
            thinking_quality=_clamp(data.get("thinking_quality", 0)),
            feedback=data.get("feedback", ""),
        )
    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[yellow]⚠ JSON 解析失败: {e}[/yellow]")
        return None


def _clamp(value: int, min_val: int = 1, max_val: int = 10) -> int:
    """Clamp a score to valid range."""
    try:
        return max(min_val, min(max_val, int(value)))
    except (TypeError, ValueError):
        return 5


def _apply_hint_penalty(
    score: ReviewScore, session: Session, challenge: Challenge
) -> ReviewScore:
    """Apply penalty for hints used.

    Each hint used reduces the average score by 0.5 points.

    Args:
        score: Original review score.
        session: Session data.
        challenge: The challenge.

    Returns:
        Adjusted ReviewScore.
    """
    if not session.hints_used:
        return score

    penalty = len(session.hints_used) * 0.5
    if penalty > 0:
        console.print(f"[yellow]⚠ 提示惩罚: 使用了 {len(session.hints_used)} 个提示，"
                       f"每个扣 0.5 分[/yellow]")

    return ReviewScore(
        correctness=max(1, int(score.correctness - penalty)),
        approach=max(1, int(score.approach - penalty)),
        code_quality=score.code_quality,  # Quality not affected by hints
        edge_cases=max(1, int(score.edge_cases - penalty)),
        thinking_quality=max(1, int(score.thinking_quality - penalty)),
        feedback=score.feedback,
    )


def _display_review(score: ReviewScore, challenge: Challenge, session: Session) -> None:
    """Display review results in a formatted panel.

    Args:
        score: The review scores.
        challenge: The challenge.
        session: The session data.
    """
    console.print()

    # Score table
    table = Table(show_header=True, header_style="bold")
    table.add_column("维度", min_width=18)
    table.add_column("评分", justify="center", min_width=8)
    table.add_column("评级", min_width=8)

    dimensions = [
        ("🎯 Correctness", score.correctness),
        ("🧭 Approach", score.approach),
        ("✨ Code Quality", score.code_quality),
        ("🔍 Edge Cases", score.edge_cases),
        ("🧠 Thinking", score.thinking_quality),
    ]

    for name, val in dimensions:
        bar = _score_bar(val)
        grade = _score_grade(val)
        table.add_row(name, f"{val}/10", f"{bar} {grade}")

    console.print(Panel(
        table,
        title=f"[bold]⭐ 评判结果 — {challenge.title}[/bold]",
        border_style="yellow",
    ))

    # Average
    avg = score.average
    console.print(f"\n  [bold]综合评分: {avg:.1f}/10[/bold] {_score_grade(avg)}\n")

    # Feedback
    if score.feedback:
        console.print(Panel(
            score.feedback,
            title="💬 反馈",
            border_style="blue",
        ))

    # Hints info
    if session.hints_used:
        console.print(f"  [yellow]💡 使用了 {len(session.hints_used)} 个提示[/yellow]")


def _export_review(
    challenge: Challenge, session: Session, journal: str
) -> None:
    """Export review context for manual AI evaluation.

    Args:
        challenge: The challenge.
        session: The session data.
        journal: Journal content.
    """
    export_text = f"""# CodeForge 评判请求

## 挑战信息
- **ID**: {challenge.id}
- **标题**: {challenge.title}
- **难度**: {challenge.difficulty.value}
- **仓库**: {challenge.repo}

## 挑战描述
{challenge.description}

## 用户的思考日志
{journal}

## 用户的代码改动
```diff
{session.user_diff}
```

## 真实解法
```diff
{session.solution_diff}
```

## 使用提示
使用了 {len(session.hints_used)}/{len(challenge.hints)} 个提示

## 评分要求
请对以下五个维度打分（每项 1-10 分）：
1. **Correctness**: 代码是否正确解决了问题？
2. **Approach**: 解题思路与真实方案的契合度
3. **Code Quality**: 代码风格、可读性、Pythonic 程度
4. **Edge Cases**: 是否考虑了边界情况
5. **Thinking Quality**: 思考日志的深度和准确性

请给出每项评分和综合反馈。
"""

    console.print(Panel(
        "[bold yellow]未配置 API key，已生成导出文本。[/bold yellow]\n\n"
        "复制下面的内容，粘贴给你喜欢的 AI 助手进行评判。\n"
        "评判后可用 [bold]forge review --score[/bold] 手动录入分数。",
        title="📋 导出模式",
        border_style="yellow",
    ))

    console.print()
    console.print(Panel(
        export_text,
        title="复制以下内容 ↓",
        border_style="dim",
    ))

    # Also save to file
    ws = workspace_path(challenge.id)
    export_path = ws / "submission" / "review_export.md"
    export_path.write_text(export_text, encoding="utf-8")
    console.print(f"\n[dim]已保存到 {export_path}[/dim]")


def save_manual_review(
    challenge_id: str,
    correctness: int,
    approach: int,
    code_quality: int,
    edge_cases: int,
    thinking_quality: int,
    feedback: str = "",
) -> bool:
    """Save a manually entered review score.

    Args:
        challenge_id: The challenge ID.
        correctness: Score 1-10.
        approach: Score 1-10.
        code_quality: Score 1-10.
        edge_cases: Score 1-10.
        thinking_quality: Score 1-10.
        feedback: Optional feedback text.

    Returns:
        True if saved successfully.
    """
    sf = session_file(challenge_id)
    if not sf.exists():
        console.print("[red]❌ 没有找到会话记录。[/red]")
        return False

    session = Session.load(sf)
    session.review = ReviewScore(
        correctness=_clamp(correctness),
        approach=_clamp(approach),
        code_quality=_clamp(code_quality),
        edge_cases=_clamp(edge_cases),
        thinking_quality=_clamp(thinking_quality),
        feedback=feedback,
    )
    session.status = SessionStatus.REVIEWED
    session.save(sf)

    console.print("[green]✅ 评分已保存。[/green]")
    return True


def _score_bar(score: float, width: int = 10) -> str:
    """Create a visual score bar.

    Args:
        score: Score value (1-10).
        width: Bar width.

    Returns:
        Colored score bar string.
    """
    filled = int(score)
    empty = width - filled
    if score >= 8:
        color = "green"
    elif score >= 5:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{'█' * filled}{'░' * empty}[/{color}]"


def _score_grade(score: float) -> str:
    """Convert a numeric score to a letter grade.

    Args:
        score: Score value (1-10).

    Returns:
        Grade string.
    """
    if score >= 9:
        return "🏆 S"
    elif score >= 8:
        return "⭐ A"
    elif score >= 6:
        return "👍 B"
    elif score >= 4:
        return "📝 C"
    else:
        return "💪 D"
