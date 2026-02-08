"""Deep retrospective engine for CodeForge.

Generates structured learning retrospectives after review:
- Thinking diagnosis: where did the user's reasoning diverge?
- Knowledge extraction: what core concepts does this bug test?
- Action guide: concrete advice for next time
- Challenge recommendation: what to practice next
"""

from __future__ import annotations

import json
import re
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .challenge import load_all_challenges
from .config import (
    load_config,
    session_file,
    journal_file,
    workspace_path,
)
from .journal import read_journal
from .models import Challenge, Session, SessionStatus

console = Console()

RETRO_PROMPT = """你是一位经验丰富的编程教练（不是代码审查员）。你的任务是帮助学生从一次 bug 修复练习中获得最大学习收益。

## 挑战描述
{description}

## 学生的思考日志（记录了他的分析思路）
```
{journal}
```

## 学生的代码改动
```diff
{user_diff}
```

## 真实解法
```diff
{solution_diff}
```

## 测试结果
{test_result}

## AI 评审评分
正确性: {correctness}/10, 方法: {approach}/10, 代码质量: {code_quality}/10, 边界: {edge_cases}/10, 思考: {thinking_quality}/10
评审反馈: {feedback}

## 可选的下一个挑战（从中选择最相关的推荐）
{available_challenges}

---

请严格按照以下 JSON 格式返回深度复盘报告（不要返回其他内容）：
```json
{{
    "thinking_diagnosis": {{
        "user_approach": "<用一句话概括学生的思路>",
        "ideal_approach": "<用一句话概括理想的解题路径>",
        "divergence_point": "<学生的思维在哪一步偏离了？具体描述>",
        "root_cause": "<这种偏离背后的根本原因是什么？是知识盲区、习惯问题还是分析方法不对？>"
    }},
    "knowledge_points": [
        "<核心知识点1：简洁描述这个bug考察了什么概念>",
        "<核心知识点2（如果有）>"
    ],
    "action_guide": [
        "<具体行动建议1：下次遇到类似问题应该怎么做>",
        "<具体行动建议2>",
        "<具体行动建议3>"
    ],
    "recommended_next": "<推荐的下一个挑战ID，从可选列表中选择最相关的，如果没有合适的填 null>"
}}
```"""


def retro_challenge(challenge: Challenge, export: bool = False) -> bool:
    """Generate a deep retrospective for a reviewed challenge.

    Args:
        challenge: The challenge to retrospect on.
        export: Force export mode even if API key is configured.

    Returns:
        True if retrospective succeeded.
    """
    sf = session_file(challenge.id)
    jf = journal_file(challenge.id)

    if not sf.exists():
        console.print("[red]❌ 没有找到会话记录。请先完成并提交挑战。[/red]")
        return False

    session = Session.load(sf)

    if session.status != SessionStatus.REVIEWED:
        console.print("[red]❌ 请先完成评审（forge review）再进行深度复盘。[/red]")
        return False

    # Check if retro already exists
    if session.retro:
        console.print("[yellow]⚠ 该挑战已有复盘报告。[/yellow]")
        _display_retro(session.retro, challenge)
        return True

    journal_content = read_journal(jf)

    config = load_config()
    api_key = config.get("api_key")
    api_provider = config.get("api_provider")

    if not export and api_key and api_provider:
        retro_data = _api_retro(
            challenge=challenge,
            session=session,
            journal=journal_content,
            provider=api_provider,
            api_key=api_key,
            model=config.get("api_model"),
        )
        if retro_data:
            session.retro = retro_data
            session.save(sf)
            _display_retro(retro_data, challenge)

            # Save retro.md
            _save_retro_markdown(retro_data, challenge)
            return True
        else:
            console.print("[yellow]⚠ API 调用失败，切换到导出模式。[/yellow]")

    # Export mode
    _export_retro(challenge, session, journal_content)
    return True


def _api_retro(
    challenge: Challenge,
    session: Session,
    journal: str,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
) -> Optional[dict]:
    """Call AI API for deep retrospective.

    Returns:
        Retro data dict if successful, None if failed.
    """
    # Build available challenges list for recommendation
    all_challenges = load_all_challenges()
    available = []
    for ch in all_challenges:
        if ch.id == challenge.id:
            continue
        ch_sf = session_file(ch.id)
        if ch_sf.exists():
            try:
                ch_session = Session.load(ch_sf)
                if ch_session.status in (SessionStatus.SUBMITTED, SessionStatus.REVIEWED):
                    continue
            except Exception:
                pass
        available.append(f"- {ch.id} ({ch.difficulty.value}): {ch.title} [tags: {', '.join(ch.tags)}]")

    available_text = "\n".join(available) if available else "（没有未完成的挑战）"

    # Test result text
    if session.test_passed is True:
        test_result = "✅ 测试通过"
    elif session.test_passed is False:
        test_result = "❌ 测试未通过"
    else:
        test_result = "未运行测试"

    review = session.review
    prompt = RETRO_PROMPT.format(
        description=challenge.description,
        journal=journal[:3000],
        user_diff=session.user_diff[:5000],
        solution_diff=session.solution_diff[:5000],
        test_result=test_result,
        correctness=review.correctness if review else "N/A",
        approach=review.approach if review else "N/A",
        code_quality=review.code_quality if review else "N/A",
        edge_cases=review.edge_cases if review else "N/A",
        thinking_quality=review.thinking_quality if review else "N/A",
        feedback=review.feedback if review else "N/A",
        available_challenges=available_text,
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
            console.print(f"[red]❌ 不支持的 API 提供商: {provider}[/red]")
            return None
    except ImportError:
        console.print("[red]❌ httpx 未安装。[/red]")
        return None
    except Exception as e:
        console.print(f"[red]❌ API 调用失败: {e}[/red]")
        return None


def _call_anthropic(prompt: str, api_key: str, model: str) -> Optional[dict]:
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
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    text = data["content"][0]["text"]
    return _parse_retro_json(text)


def _call_openai(prompt: str, api_key: str, model: str) -> Optional[dict]:
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
            "max_tokens": 2048,
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    return _parse_retro_json(text)


def _call_openrouter(prompt: str, api_key: str, model: str) -> Optional[dict]:
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
            "max_tokens": 2048,
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    return _parse_retro_json(text)


def _parse_retro_json(text: str) -> Optional[dict]:
    """Parse retrospective JSON from AI response."""
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        console.print("[yellow]⚠ 无法从 AI 响应中提取 JSON。[/yellow]")
        return None

    try:
        data = json.loads(json_match.group())

        # Validate required fields
        required = ["thinking_diagnosis", "knowledge_points", "action_guide"]
        for field in required:
            if field not in data:
                console.print(f"[yellow]⚠ 复盘报告缺少字段: {field}[/yellow]")
                return None

        return data
    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[yellow]⚠ JSON 解析失败: {e}[/yellow]")
        return None


def _display_retro(retro: dict, challenge: Challenge) -> None:
    """Display the retrospective report in a rich format."""
    console.print()

    # Thinking Diagnosis
    diag = retro.get("thinking_diagnosis", {})
    diag_text = Text()
    diag_text.append("你的思路: ", style="dim")
    diag_text.append(diag.get("user_approach", "—"), style="white")
    diag_text.append("\n\n")
    diag_text.append("理想路径: ", style="dim")
    diag_text.append(diag.get("ideal_approach", "—"), style="green")
    diag_text.append("\n\n")
    diag_text.append("偏离点:   ", style="dim")
    diag_text.append(diag.get("divergence_point", "—"), style="yellow")
    diag_text.append("\n\n")
    diag_text.append("根本原因: ", style="dim")
    diag_text.append(diag.get("root_cause", "—"), style="red")

    console.print(Panel(
        diag_text,
        title="[bold]🔍 思路诊断[/bold]",
        border_style="cyan",
    ))

    # Knowledge Points
    kps = retro.get("knowledge_points", [])
    if kps:
        kp_text = Text()
        for i, kp in enumerate(kps):
            kp_text.append(f"  {i+1}. ", style="bold cyan")
            kp_text.append(kp, style="white")
            if i < len(kps) - 1:
                kp_text.append("\n")

        console.print(Panel(
            kp_text,
            title="[bold]📚 核心知识点[/bold]",
            border_style="blue",
        ))

    # Action Guide
    actions = retro.get("action_guide", [])
    if actions:
        action_text = Text()
        for i, action in enumerate(actions):
            action_text.append(f"  {i+1}. ", style="bold green")
            action_text.append(action, style="white")
            if i < len(actions) - 1:
                action_text.append("\n")

        console.print(Panel(
            action_text,
            title="[bold]🎯 行动指南[/bold]",
            border_style="green",
        ))

    # Recommended Next
    rec = retro.get("recommended_next")
    if rec and rec != "null":
        console.print(f"\n  [bold]📋 推荐下一个挑战:[/bold] [cyan]{rec}[/cyan]")
        console.print(f"  运行 [bold]forge start --id {rec}[/bold] 开始\n")
    else:
        console.print()


def _save_retro_markdown(retro: dict, challenge: Challenge) -> None:
    """Save retrospective as a markdown file."""
    ws = workspace_path(challenge.id)
    retro_path = ws / "submission" / "retro.md"
    retro_path.parent.mkdir(parents=True, exist_ok=True)

    diag = retro.get("thinking_diagnosis", {})
    kps = retro.get("knowledge_points", [])
    actions = retro.get("action_guide", [])
    rec = retro.get("recommended_next")

    md = f"""# 深度复盘 — {challenge.title}

## 思路诊断

- **你的思路**: {diag.get("user_approach", "—")}
- **理想路径**: {diag.get("ideal_approach", "—")}
- **偏离点**: {diag.get("divergence_point", "—")}
- **根本原因**: {diag.get("root_cause", "—")}

## 核心知识点

{chr(10).join(f"- {kp}" for kp in kps)}

## 行动指南

{chr(10).join(f"{i+1}. {a}" for i, a in enumerate(actions))}

## 推荐下一个挑战

{f"→ {rec}" if rec and rec != "null" else "暂无推荐"}
"""

    retro_path.write_text(md, encoding="utf-8")
    console.print(f"[dim]复盘报告已保存到 {retro_path}[/dim]")


def _export_retro(
    challenge: Challenge, session: Session, journal: str
) -> None:
    """Export retro context for manual evaluation."""
    review = session.review
    export_text = f"""# CodeForge 深度复盘请求

## 挑战信息
- **ID**: {challenge.id}
- **标题**: {challenge.title}
- **难度**: {challenge.difficulty.value}

## 挑战描述
{challenge.description}

## 学生的思考日志
{journal}

## 学生的代码改动
```diff
{session.user_diff}
```

## 真实解法
```diff
{session.solution_diff}
```

## 评审评分
- 正确性: {review.correctness if review else "N/A"}/10
- 方法: {review.approach if review else "N/A"}/10
- 代码质量: {review.code_quality if review else "N/A"}/10
- 边界情况: {review.edge_cases if review else "N/A"}/10
- 思考质量: {review.thinking_quality if review else "N/A"}/10
- 反馈: {review.feedback if review else "N/A"}

## 请按以下结构给出深度复盘：

1. **思路诊断**：对比学生思考日志中的思路和真实解法，指出学生的思维在哪一步偏离了正确方向，以及偏离的根本原因
2. **核心知识点**：这个 bug 考察了什么核心编程概念或知识点
3. **行动指南**：给出 2-3 条具体的"下次遇到类似问题应该怎么做"的建议
"""

    console.print(Panel(
        "[bold yellow]未配置 API key，已生成导出文本。[/bold yellow]\n\n"
        "复制下面的内容，粘贴给你喜欢的 AI 助手进行深度复盘。",
        title="📋 导出模式",
        border_style="yellow",
    ))

    console.print()
    console.print(Panel(
        export_text,
        title="复制以下内容 ↓",
        border_style="dim",
    ))

    ws = workspace_path(challenge.id)
    export_path = ws / "submission" / "retro_export.md"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(export_text, encoding="utf-8")
    console.print(f"\n[dim]已保存到 {export_path}[/dim]")
