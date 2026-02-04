"""Thinking journal system for CodeForge.

Manages the journal.md file that users must fill out before submitting.
Includes template generation and content validation.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.console import Console

from .models import Challenge

console = Console()

JOURNAL_TEMPLATE = """# 🧠 思考日志 — {title}

> 提交前必须填写。记录你的思考过程，这是最有价值的练习环节。

## 问题分析

### 问题的根本原因是什么？

<!-- 在这里写下你的分析 -->


### 你观察到了什么症状/现象？

<!-- 描述 bug 的表现 -->


## 解决方案

### 你打算用什么方法解决？为什么？

<!-- 描述你的解决思路 -->


### 可能有哪些边界情况？

<!-- 列出你能想到的边界情况 -->


### 你预期改动哪些文件？

<!-- 列出你计划修改的文件 -->


## 反思（提交后填写）

### 实际改动和预期有什么不同？

<!-- 如果有的话 -->


### 你学到了什么？

<!-- 总结 -->

"""

# Markers that indicate template-only content (not yet filled)
TEMPLATE_MARKERS = [
    "<!-- 在这里写下你的分析 -->",
    "<!-- 描述 bug 的表现 -->",
    "<!-- 描述你的解决思路 -->",
    "<!-- 列出你能想到的边界情况 -->",
    "<!-- 列出你计划修改的文件 -->",
]

# Minimum content length beyond template to be considered "filled"
MIN_CONTENT_LENGTH = 50


def create_journal_template(path: Path, challenge: Challenge) -> None:
    """Create a journal.md template for a challenge.

    Args:
        path: Where to write the journal file.
        challenge: The challenge this journal is for.
    """
    content = JOURNAL_TEMPLATE.format(title=challenge.title)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def open_journal(path: Path) -> None:
    """Open the journal file in the user's preferred editor.

    Uses $EDITOR environment variable, falls back to vim.

    Args:
        path: Path to the journal file.
    """
    editor = os.environ.get("EDITOR", "vim")

    if not path.exists():
        console.print("[red]❌ journal.md 不存在。请先运行 forge start。[/red]")
        return

    console.print(f"[dim]使用 {editor} 打开 journal.md...[/dim]")
    try:
        subprocess.run([editor, str(path)], check=False)
    except FileNotFoundError:
        console.print(f"[red]❌ 编辑器 '{editor}' 未找到。[/red]")
        console.print("设置 EDITOR 环境变量或运行 [bold]forge config set editor <编辑器>[/bold]")


def validate_journal(path: Path) -> tuple[bool, str]:
    """Validate that the journal has been meaningfully filled out.

    Checks that:
    1. The file exists
    2. Template placeholders have been replaced with real content
    3. Minimum content length is met

    Args:
        path: Path to the journal file.

    Returns:
        Tuple of (is_valid, reason_if_invalid).
    """
    if not path.exists():
        return False, "journal.md 不存在。请先运行 forge start 和 forge think。"

    content = path.read_text(encoding="utf-8")

    # Strip template markers and headings to measure real content
    real_content = content
    for marker in TEMPLATE_MARKERS:
        real_content = real_content.replace(marker, "")

    # Remove markdown headings and blank lines
    lines = real_content.split("\n")
    content_lines = [
        line for line in lines
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith(">")
        and not line.strip().startswith("---")
        and not line.strip().startswith("<!--")
    ]

    real_text = "\n".join(content_lines).strip()

    if len(real_text) < MIN_CONTENT_LENGTH:
        return False, (
            f"思考日志内容不足（当前 {len(real_text)} 字符，最少 {MIN_CONTENT_LENGTH} 字符）。\n"
            "请运行 [bold]forge think[/bold] 填写你的思考过程。"
        )

    # Check if at least some template markers have been replaced
    remaining_markers = sum(1 for m in TEMPLATE_MARKERS if m in content)
    if remaining_markers >= len(TEMPLATE_MARKERS):
        return False, (
            "思考日志看起来还是模板状态，没有实质内容。\n"
            "请运行 [bold]forge think[/bold] 填写你的分析和思路。"
        )

    return True, ""


def read_journal(path: Path) -> str:
    """Read the journal content.

    Args:
        path: Path to the journal file.

    Returns:
        Journal content as string, or empty string if not found.
    """
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
