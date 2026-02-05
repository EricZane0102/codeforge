# 🔥 CodeForge — 编码能力锻造 CLI

从真实开源项目中抓取已解决的 bug，让你在无 AI 辅助下独立解决，然后对比真实方案 + AI 评判，系统性重建深度编码能力。

## 安装

```bash
# 克隆仓库
git clone https://github.com/EricZane0102/codeforge.git
cd codeforge

# 安装（开发模式）
pip install -e .

# 初始化
forge init
```

## 快速开始

```bash
# 1. 获取一个挑战
forge challenge --difficulty easy

# 2. 开始挑战（下载仓库、初始化工作区）
forge start --id httpx-url-quoting

# 3. 先写思考日志（必须填写才能提交）
forge think

# 4. 修改代码（在 ~/.codeforge/workspaces/<id>/repo/ 目录下）

# 5. 提交你的方案
forge submit

# 6. 对比真实解法
forge compare

# 7. AI 评判
forge review

# 8. 查看统计
forge stats
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `forge init` | 初始化 CodeForge 工作目录 |
| `forge list` | 列出所有可用挑战 |
| `forge challenge` | 获取一个编码挑战 |
| `forge start --id <id>` | 开始挑战 |
| `forge think` | 打开思考日志 |
| `forge hint` | 获取提示（影响评分 -0.5/个） |
| `forge submit` | 提交方案 |
| `forge compare` | 对比真实解法 |
| `forge review` | AI 评判 |
| `forge review --export` | 导出评判文本（手动贴给 AI） |
| `forge review --score` | 手动录入评分 |
| `forge stats` | 查看统计数据 |
| `forge reset --id <id>` | 重置一个挑战 |
| `forge config` | 查看/修改配置 |
| `forge version` | 显示版本 |

## 配置 API 评判

```bash
# Anthropic
forge config api_provider anthropic
forge config api_key sk-ant-xxxxx
forge config api_model claude-sonnet-4-20250514

# OpenAI
forge config api_provider openai
forge config api_key sk-xxxxx
forge config api_model gpt-4o

# OpenRouter（统一接入多家模型）
forge config api_provider openrouter
forge config api_key sk-or-xxxxx
forge config api_model anthropic/claude-sonnet-4   # 或 openai/gpt-4o 等
```

OpenRouter 支持 200+ 模型，通过统一 API 访问 Anthropic、OpenAI、Google 等多家供应商。
注册获取 key: https://openrouter.ai/keys

没配 API key 也能用！`forge review` 会生成格式化文本，你可以复制粘贴给任意 AI 助手评判。

## 工作流程

```
forge challenge → forge start → forge think → 修改代码 → forge submit → forge compare → forge review
                                    ↑
                              forge hint（可选）
```

## 评分维度（每项 1-10 分）

| 维度 | 说明 |
|------|------|
| 🎯 Correctness | 代码是否正确解决了问题 |
| 🧭 Approach | 解题思路与真实方案的契合度 |
| ✨ Code Quality | 代码风格、可读性、Pythonic 程度 |
| 🔍 Edge Cases | 是否考虑了边界情况 |
| 🧠 Thinking | 思考日志的深度和准确性 |

## 添加自定义挑战

创建 YAML 文件到 `~/.codeforge/challenges/`：

```yaml
id: my-challenge-001
title: "Fix some bug"
repo: owner/repo
difficulty: easy  # easy | medium | hard
time_limit: 30    # minutes
description: |
  描述 bug 的症状和预期行为...
setup:
  base_commit: "abc123"      # bug 存在时的 commit
  solution_commit: "def456"  # 修复后的 commit
  test_command: "pytest tests/ -x"
  files_of_interest:
    - path/to/relevant/file.py
tags: [bug-fix, web]
hints:
  - "第一个提示"
  - "第二个提示"
  - "第三个更详细的提示"
```

## 目录结构

```
~/.codeforge/
├── config.yaml          # 配置文件
├── challenges/          # 挑战 YAML 文件
├── repos/               # Git 仓库缓存
├── workspaces/          # 工作目录
│   └── <challenge-id>/
│       ├── repo/        # 代码仓库（checkout 到 bug 状态）
│       ├── journal.md   # 思考日志
│       ├── session.json # 会话状态
│       └── submission/  # 提交的 diff
└── history.json         # 历史记录
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest
```

## License

MIT
