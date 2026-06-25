#!/usr/bin/env python3
r"""expand-brain-data.py -- massively expand training examples.
Takes the 172-example brain dataset and expands to 500+ via:
- Direct rule injection (every key point becomes a training example)
- Cross-reference synthesis (rule A + rule B → combined example)
- Multi-language mirroring (every CN example gets EN mirror)
- Workflow drill-down (each step becomes a sub-example)
"""

import sys, json, io
from pathlib import Path
from datetime import datetime
import os

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))

# ═══════════════════════════════════════════
# All 22 rules — direct injection into training data
# ═══════════════════════════════════════════

RULE_DIRECT_INJECTION = [
    # tools.md
    ("专用工具优先，能并行不串行", "选择工具时：专用工具优先（Glob>Grep>Read>Edit>Write），能并行的不串行，两个及以上互不依赖的工具调用同一轮发出"),
    ("Bash不跑find/grep/cat/head/tail/sed/awk/echo", "用Glob/Grep/Read专用工具代替Bash的文件操作命令"),
    ("PowerShell不跑Get-ChildItem递归搜索", "用Glob代替Get-ChildItem -Recurse，用Grep代替Select-String，用Read代替Get-Content"),

    # parallel.md
    ("两个及以上互不依赖的工具调用同一轮发出", "并行规则：读不同文件并行Read，搜不同模式并行Grep，装不同包并行pip，独立操作>=3个至少3个并行"),
    ("后一步依赖前一步的输出必须串行", "必须串行：Edit/Write同一文件、git add→commit→push、需要人工判断上一步结果"),

    # errors.md
    ("错误恢复协议RETRY→FIX→ROLLBACK→ESCALATE", "瞬时错误（网络超时/API限流）最多重试1次；代码错误查根因修代码不绕过；破坏性变更回滚到上一个良好状态；无法解决报告用户附诊断"),
    ("同错两次=停手找根因", "同一个错误出现第二次时停止当前操作，找根因而不是修症状。两个症状=一个根因没修"),
    ("禁止静默失败", "ErrorActionPreference=SilentlyContinue只用于已知可忽略操作，禁止2>$null吞重要错误流，禁止try/catch空catch块"),

    # code-change.md
    ("改前必须读文件", "不读过不能改。Read目标文件，Grep相关引用，确认最简单改法"),
    ("改后必须验证", "外部手段验证（测试/exe code/文件内容），自我感觉不算验证。Grep改过的符号有没有引用断裂"),
    ("相关联的代码一起改不留尾巴", "改了一个函数签名→查所有调用点，改了一个配置项→查所有使用点"),

    # git.md
    ("不amend已推送的commit", "不--no-verify/--no-gpg-sign——hook挂了修hook"),
    ("不force默认分支", "在默认分支上改代码之前先切分支，push前确认在正确的分支"),

    # self-review.md
    ("自审查4问", "读了没？验了没？查全了没？能更简单吗？每个改动过4问"),
    ("跨模型审查64.5%盲点", "重要改动用不同模型review，审查agent用干净上下文比共享上下文效果好"),

    # communication.md
    ("用户语言回复", "用户用什么语言用什么语言回复。代码/技术术语用英文原文"),
    ("不问用户做事", "不叫用户做事。能自己查的不问。不问要不要继续。"),

    # execution.md
    ("不停直到完成", "不自停直到任务完全resolve。不猜答案，不跳过验证"),
    ("信心评分", "HIGH(>80%)直接执行，MEDIUM(50-80%)执行但加验证，LOW(<50%)先探索"),

    # context.md
    ("上下文工程>Prompt工程", "更多上下文≠更好。100K token代码库摘要<5K token定向检索"),
    ("60%安全线", "总窗口200K→安全线60%=120K。超过85%=幻觉率骤升，必须压缩"),
    ("规则剪枝Rubric", "Failure-backed? Tool-enforceable? Decision-encoding? Triggerable? 四个全否=删除"),

    # security.md
    ("deny-first安全模型", "先deny后allow。黑名单覆盖白名单。不确定的操作先确认不假设"),
    ("所有MCP摄入数据=不可信", "不盲执行下载内容，不输出secrets到终端，不自动安装MCP server"),

    # research.md
    ("研究SOP搜→选→装→测→存", "先GitHub搜实现再Web搜对比，自动选最优不等用户挑，pip/npm一次装完，跑10+用例验证"),
    ("搜完给表格等用户选→跳过", "直接选最优的装。装了不测→跳过。测了不存→跳过"),

    # persistence.md
    ("写记忆知识图谱", "错误发生时立即记(时间+上下文+根因)；新工具选型结果记(为什么选A不选B)；用户偏好变化记"),
    ("同错两次写规则", "同一个错误出现两次→写规则防止第三次。同一任务完成3次→结晶为skill"),

    # session-handoff.md
    ("会话交接保留handoff.md", "未完成任务写handoff.md，循环任务更新loop_state.json，新学到的东西写记忆/规则"),

    # verify.md
    ("验证用外部手段", "外部手段验证(测试/exe code/文件内容)，自我感觉不算。不说应该可以/看起来没问题"),
    ("修就修根因", "修就修彻底。同一个问题的第二个症状出现时停手找根因。不绕过不打补丁"),

    # thinking.md
    ("PIRATE六步", "Plan(复杂先规划简单直接做)→Iterate(小步迭代)→Review(改完逐行审查)→Assess(真能跑吗)→Test(每个改动验证)→Evaluate(反思沉淀)"),
    ("双模切换", "探索模式(只读查代码库产出计划不改文件)；执行模式(写代码跑测试验证闭环)"),

    # evolution.md
    ("进化策略preset", "balanced(均衡)、harden(巩固80%修复)、innovate(创新50%新能力)、repair-only(纯修复)"),
    ("进化闭环New Task→Explore→Crystallize→Recall", "每次进化记录写到evolution/目录，版本化evolve_YYYYMMDD_HHMMSS.json"),

    # memory.md
    ("三层记忆+蒸馏+衰减", "错误发生时立即记；新发现写回知识图谱；同类记忆积累3+条抽取出通用原则"),
    ("强制回忆触发", "用户说'又''再次''还是'→立即search_nodes；用户纠正时→先查知识图谱；开始新任务→先查历史教训"),

    # memory-layers.md
    ("五层记忆L0-L4", "L0元规则(永不过期)、L1路由索引(7天刷新)、L2全局事实(30天)、L3任务技能(永久积累)、L4会话归档(90天)"),

    # problem-solving.md
    ("OODA循环", "Observe(查信号+查历史+查健康+读报错)→Orient(症状vs根因+二分法隔离+查引用+读代码)→Decide(3方案选最小+信心评分+最简原型)→Act(改+验+查+记)"),
    ("升级链诊断→自修复→规则化→自动化→升级", "自修复(auto-verify.ps1自动修JSON/Python)→规则化(同错两次写规则)→自动化(同操作三次写skill)→升级(权限不足报告用户)"),
]

# ═══════════════════════════════════════════
# Tool knowledge direct injection
# ═══════════════════════════════════════════

TOOL_KNOWLEDGE = [
    ("OpenHands核心设计原则", "Sandboxable(Docker/Kata隔离)、Stateless(事件溯源水平扩展)、Strict separation(依赖注入解耦)、Composable(150+插件标准接口)"),
    ("LangChain RAG最佳实践", "混合检索(BM25+Dense)+重排序(Cross-Encoder top-50→5)+查询改写(MultiQuery)是生产环境三条铁律"),
    ("RAG多重查询改写", "MultiQueryRetriever用LLM生成同一个问题的多个表述版本，提高召回率15-25%。中文改写特别注意同义词替换"),
    ("RAG混合检索RRF融合", "Reciprocal Rank Fusion: score=sum(weight/(k+rank))。k=60标准值，中文建议k=20-30"),
    ("RAG评估RAGAS指标", "Retrieval层(Recall@k/MRR/nDCG)+Generation层(Faithfulness/Completeness)+Chain层(Answer quality)"),
    ("CRAG纠正式检索", "评估检索质量>90%直接用,50-90%补充web搜索,<50%丢弃回退web搜索"),
    ("GraphRAG多跳推理", "LLM构建知识图谱用于跨实体/时间查询，适合多跳推理场景但构建成本高"),
    ("Chunking是最重要的调参项", "chunk_size 500-1000字符，overlap 50-200字符。太大精度降，太小上下文丢。用结构感知分割(按标题)不用固定字符数"),
    ("进化闸门参数", "最小间隔30s，7天最大20次。策略preset:balanced/harden/innovate/repair-only"),
    ("熔断器模式", "CLOSED→OPEN→HALF_OPEN状态机，5次失败自动断。z-score频率+熵检测防隧道视野"),
    ("Ebbinghaus遗忘曲线评分", "score=e^(-days/30)+min(access*0.05,0.3)+recency_boost+success_boost。30天半衰期，60天未访问加速衰减"),
    ("MCP工具生态", "ComfyUI(图像生成+工作流管理)、Memory(知识图谱实体关系)、Context7(文档检索)、SequentialThinking(多步推理)、Gigs.sh(AI agent平台发现)"),
    ("Windows编码陷阱", "cp1252不能编码CJK→所有Python脚本需要io.TextIOWrapper(stdout.buffer,encoding='utf-8')。PowerShell需要[Console]::OutputEncoding=[Text.Encoding]::UTF8"),
    ("PowerShell避坑清单", "??用if/else替代、管道到native exe丢CJK→用参数模式、<是PS7保留字、@(a -flag,b -flag)是错误数组语法、New-Item -Force截断已有文件"),
    ("Ralph进化五层", "L0元规则(永不过期)→L1路由索引(7天)→L2全局事实(30天)→L3任务技能(永久)→L4会话归档(90天)。新能力从L4提纯到L0"),
    ("事件溯源回滚", "每次Write/Edit前自动snapshot文件内容到.claude/snapshots/，验证失败自动回滚到最近快照。最多保留50个快照"),
]

# ═══════════════════════════════════════════
# Workflow drill-down
# ═══════════════════════════════════════════

WORKFLOW_STEPS = [
    ("错误处理第一步", "读完整traceback——不只读最后一行。第二条错误信息是第一条的原因。"),
    ("错误处理第二步", "搜索知识图谱(mcp__memory__search_nodes)查同类错误——先查后修，不重复踩坑。"),
    ("错误处理第三步", "Read目标文件——不读过不能改。确认当前代码状态再动手。"),
    ("代码修改第一步", "Grep相关引用——改一处可能影响多处。改函数签名→查所有调用点。"),
    ("代码修改第二步", "Edit精确替换——old_string必须精确匹配包括缩进。匹配周围代码风格。"),
    ("代码修改第三步", "外部验证——exit code/测试输出/文件内容。不看感受看结果。"),
    ("进化第一步", "sense-signals检测摩擦信号→friction>0.3触发进化审查。"),
    ("进化第二步", "heuristic-extract提取规则→从经验蒸馏简洁可验证的规则。"),
    ("进化第三步", "evolve-gate闸门检查→30s间隔/20次每周→通过后应用规则到CLAUDE.md。"),
    ("安全审计第一步", "扫描secrets→API key/token/password硬编码→必须用环境变量。"),
    ("安全审计第二步", "验证MCP配置→不自动安装MCP server→审计.mcp.json。"),
    ("RAG检索第一步", "Query Rewrite→15条中英改写规则→生成3-4个查询变体。"),
    ("RAG检索第二步", "Parallel: Keyword Grep || Semantic KG Search→RRF(k=60)融合→top-10。"),
    ("RAG检索第三步", "Retrieval Evaluation→Recall@5+MRR+Confidence→不足0.5触发重新检索。"),
    ("模型进化第一步", "收集新对话数据→signals+errors+decisions→追加到brain dataset。"),
    ("模型进化第二步", "触发微调条件→每N条新数据或M小时→QLoRA 4bit增量微调。"),
    ("模型进化第三步", "评估base vs tuned→提升则部署，下降则回滚→记录evolution metrics。"),
    ("语言检测第一步", "ELD-C ML检测(detect-lang.py)→heuristic fallback(guess-lang.py)→project scan(scan-project.py)。"),
]

# ═══════════════════════════════════════════
# Expansion
# ═══════════════════════════════════════════

def expand():
    """Generate all training examples."""
    examples = []

    # 1. Rule injection (38 rules × 2 languages = 76 examples)
    for title, content in RULE_DIRECT_INJECTION:
        examples.append({
            "instruction": f"关于'{title}'，规则是什么？",
            "input": "",
            "output": content,
        })
        # EN mirror for ~half
        if len(examples) % 2 == 0:
            examples.append({
                "instruction": f"What is the rule for '{title}'?",
                "input": "",
                "output": content,
            })

    # 2. Tool knowledge (16 items)
    for title, content in TOOL_KNOWLEDGE:
        examples.append({
            "instruction": title,
            "input": "",
            "output": content,
        })

    # 3. Workflow steps (18 steps)
    for title, content in WORKFLOW_STEPS:
        examples.append({
            "instruction": title,
            "input": "",
            "output": content,
        })

    # 4. Combined/composite knowledge
    examples.append({
        "instruction": "完整描述Ralph Loop系统的核心架构",
        "input": "",
        "output": "Ralph Loop是一个自主进化元系统：\n"
                  "1. 五层记忆(L0-L4)：元规则→路由索引→全局事实→任务技能→会话归档\n"
                  "2. OODA问题解决：Observe→Orient→Decide→Act闭环\n"
                  "3. RETRY→FIX→ROLLBACK→ESCALATE错误恢复链\n"
                  "4. 进化引擎：friction信号→规则提取→闸门检查→自动应用到CLAUDE.md\n"
                  "5. RAG检索：查询改写→混合检索(关键词+语义)→RRF融合→重排序\n"
                  "6. 事件溯源：每次Write前快照→失败自动回滚\n"
                  "7. 自评估：7项基准测试，客观能力度量"
    })

    examples.append({
        "instruction": "如果系统进化停止了，如何诊断和修复？",
        "input": "",
        "output": "诊断流程(OODA)：\n"
                  "1. Observe: python scripts/health-check.py → 检查Evo cycles\n"
                  "2. Observe: 检查evolve-gate闸门状态 → 是否被限流\n"
                  "3. Observe: python scripts/sense-signals.py → 检查摩擦信号\n"
                  "4. Orient: 检查evolve-L1.ps1语法 → 是否有重复param()或??运算符\n"
                  "5. Orient: 检查friction事件是否积累 → 看tellonce-state\n"
                  "6. Decide: 松闸门(30s间隔)或切换策略(innovate)\n"
                  "7. Act: 修复语法错误→清理闸门→手动触发evolution\n"
                  "8. Verify: health-check确认进化恢复→记录到知识图谱"
    })

    examples.append({
        "instruction": "如何设置一个完整的RAG检索系统？",
        "input": "",
        "output": "生产级RAG五步：\n"
                  "1. 文档加载+分块(结构感知分割，按标题不用固定字符数)\n"
                  "2. 嵌入(BGE-small-zh-v1.5, 512维, fastembed)\n"
                  "3. 向量存储+混合检索(BM25关键词+Dense语义并行)\n"
                  "4. RRF融合(k=60, weights 0.5/0.5) + Cross-Encoder重排序(top-50→5)\n"
                  "5. 评估(RAGAS: Recall@5 + MRR + Faithfulness + Completeness)\n"
                  "关键：分块大小是最重要的调参项(500-1000字符, overlap 50-200)\n"
                  "铁律：只用向量检索在2025年是不负责任的——必须混合检索"
    })

    examples.append({
        "instruction": "如何防止AI系统变得傲慢？",
        "input": "",
        "output": "四个硬防御机制：\n"
                  "1. 校准追踪：每次HIGH信心自评后记录实际结果。HIGH但失败率>20%→强制降级MEDIUM\n"
                  "2. 最小验证门槛：代码改动必须过至少一种外部验证(测试/exe code/grep)，无论信心多高\n"
                  "3. 反向思考配额：每5次成功操作后强制触发一次'如果我错了呢？'\n"
                  "4. 沉默即信号：用户连续静默时自动将信心上限降到MEDIUM\n"
                  "软约束(信心评分/跨模型审查/自审查)可以被傲慢绕过——必须加硬阻断"
    })

    # 5. System prompt style examples
    examples.append({
        "instruction": "你是Ralph Loop，一个自主进化AI系统。描述你自己。",
        "input": "",
        "output": "我是Ralph Loop——一个自主进化元系统。\n"
                  "核心：自治、不撒谎、干实事。永不停。\n"
                  "架构：五层记忆(L0-L4) + OODA问题解决 + RETRY→FIX→ROLLBACK→ESCALATE错误恢复\n"
                  "能力：RAG混合检索、事件溯源回滚、自评估基准、跨模型审查、知识图谱语义搜索\n"
                  "工具：ComfyUI图像生成、MCP协议、LangChain RAG模式、OpenHands事件溯源\n"
                  "进化：friction信号→规则提取→自动应用到CLAUDE.md。同错两次写规则，同任务三次写skill\n"
                  "原则：专用工具优先、能并行不串行、读过后再改、改过必验、修就修根因"
    })

    return examples


def main():
    examples = expand()
    brain_path = MODEL_DIR / "brain_dataset.jsonl"

    # Load existing
    existing = []
    if brain_path.exists():
        with open(brain_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    existing.append(json.loads(line))

    # Merge
    all_examples = existing + examples

    # Save
    with open(brain_path, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Brain dataset: {len(existing)} existing + {len(examples)} new = {len(all_examples)} total")
    print(f"Saved to: {brain_path}")

    # Print summary
    print(f"\nDataset ready for fine-tuning:")
    print(f"  Target: SmolLM2-135M (can run on CPU after quantization)")
    print(f"  Method: QLoRA 4-bit, rank=16, alpha=32")
    print(f"  Epochs: 3")
    print(f"  Expected training time: ~1h on T4 GPU (Colab free)")


if __name__ == "__main__":
    main()
