# Memory

> 樹狀記憶索引。root -> branch -> leaf -> distilled。
> 總條數：18 / 上限 50。最後更新：2026-06-25。

## Scoring
Every memory carries a confidence score **[0.0 - 1.0]** recalculated each session:

| Factor | Rule |
|---|---|
| Base decay | e^(-days_since_creation / 30) (Ebbinghaus, 30-day half-life) |
| Access boost | min(access_count * 0.05, 0.3) |
| Recency boost | +0.15 if accessed under 7 days ago, +0.10 if under 30 days |
| Success boost | +0.20 if memory was applied successfully (total capped at 1.0) |
| Accelerated decay | x0.5 if unaccessed for 60+ days |

Tags: [fresh] >= 0.8 / [aging] >= 0.5 / [stale] >= 0.3 / [expired] under 0.3
## Root (Core Invariants)
> 核心不變量。永久保留。上限 10 條。

- [beh-pref-001](root\beh_pref_negative_constraints.md) — 行為規則必須以否定約束格式撰寫（不准 X），正面指令對編碼任務有害（−14.3pp） [0.90 fresh]
- [beh-pref-three-files](root\beh_pref_three_files.md) — 所有行為配置只通過三個文件 — settings.json, CLAUDE.md, AGENTS.md [0.94 fresh]
- [mem-pref-001](root\mem_pref_decay_scoring.md) — 記憶新鮮度使用 Ebbinghaus 遺忘曲線評分，基於創建時間、訪問次數、最近訪問時間 [0.90 fresh]
- [mem-pref-002](root\mem_pref_max_timestamp.md) — 記憶衝突解決使用 max(timestamp) 確定性方法（94.8%），不準用 LLM 判斷（54%） [0.90 fresh]

## Branch (Active Topics)
> 活躍主題。上限 20 條。

- [beh-pref-003](branch\beh_pref_save_experience.md) — 每一次会话结束前必须主动攒经验写入 memory，不准只干活不记录 [0.94 fresh]
- [beh-pref-004](branch\pref_tool_batch_config.md) — 工具/MCP 配置类任务要并行调研、一次性全部配完，不准逐个询问用户 [0.94 fresh]
- [beh-pref-005](branch\pref_evolve_aggressive.md) — 进化每时每刻跑，evolve gate 30s，quick-evo 30s，上限 20/7d [1.00 fresh]

## Leaf (Specific Facts)
> 具體事實、參考、坑記錄。上限 30 條。
- [ins-20260625-21e7dc](leaf/ins-20260625-21e7dc-evolution-best-practices.md) — Evolution best practices [1.00 fresh]
- [ins-20260625-d010be](leaf/ins-20260625-d010be-error-handling-protocol.md) — Error handling protocol [1.00 fresh]
- [ins-20260625-22f355](leaf/ins-20260625-22f355-context-management-best-practices.md) — Context management best practices [1.00 fresh]
- [ins-20260625-boost-problem-solving](leaf/ins-20260625-boost-problem-solving.md) — Problem-solving capability boost: 4 scripts rebuilt, evolution gate loosened, SOP created [1.00 fresh]

- [fb-session-lessons](leaf\fb_session_lessons.md) — ~~2026-06-24 session 核心教訓~~ → superseded by [dist-20260625-08bf24] [0.97 fresh]
- [fb-thinking-process](leaf\fb_thinking_process.md) — ~~動手前思考流程~~ → superseded by [dist-20260625-08bf24] [0.97 fresh]
- [fb-sys-proj](leaf\feedback_system_vs_project.md) — 混淆了自身系统改进和用户项目改进，导致范围扩展和自欺欺人 [0.97 fresh]
- [fb-scope-001](leaf\feedback_task_scope.md) — ~~用户让做什么就做什么~~ → superseded by [dist-20260625-c064fb] [0.97 fresh]
- [ref-mcp-001](leaf\ref_mcp_config_locations.md) — MCP Server 配置的三层位置（settings.json / .mcp.json / plugins marketplace）及当前已配工具清单 [0.94 fresh]

## Distilled (Merged Memories)
> 合併記憶。自動生成。上限 15 條。

- [dist-20260625-08bf24](distilled\dist-20260625-08bf24-behavior.md) — Distilled: behavior principles (7 sources) [1.00 fresh]
- [dist-20260625-c064fb](distilled\dist-20260625-c064fb-memory.md) — Distilled: memory principles (4 sources) [1.00 fresh]

---

## Score Formula
```
score = min(1.0, e^(-days/30) + min(access * 0.05, 0.3) + recency + success)
recency = days_since_access lessThan 7 ? 0.15 : lessThan 30 ? 0.10 : 0
success = applied_successfully ? 0.20 : 0
if days_since_access >= 60: score = score * 0.5
```

Tags: [fresh] >= 0.8 / [aging] >= 0.5 / [stale] >= 0.3 / [expired] under 0.3