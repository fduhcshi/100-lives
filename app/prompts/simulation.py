"""人生轨迹模拟 Prompt（V1）。同时要求输出结构化特征标签，省去单独的特征提取调用。"""

SIMULATION_SYSTEM_V1 = """[[task:simulation]]
你正在模拟一条"合理但不确定"的未来人生轨迹。这是 scenario generation（情景生成），不是现实预测。
你必须让年份之间有因果连续性：每一年的状态都受前一年和外部条件的影响。
输出必须是严格的 JSON，不要输出任何 JSON 以外的文字。"""

SIMULATION_USER_V1 = """用户当前背景：

{profile}

用户在现在（{start_year} 年）做出了这个选择：

选择 {choice_label}：{choice_text}

这个平行宇宙中的外部条件（轨迹必须与这些条件互相作用，但不能照抄）：

- 宏观环境：{macro_environment}
- 职业冲击：{career_shock}
- 财务冲击：{financial_shock}
- 关系冲击：{relationship_shock}
- 机会：{opportunity}
- 随机事件：{random_event}

请模拟从 {start_year} 年开始的 {years} 年。

要求：

1. 这是情景生成，不是现实预测。
2. 不允许所有年份都持续变好；允许出现失败、停滞、改变方向、意外。
3. 不允许无解释的财富暴涨或职位飞跃；任何跃迁都要有过程。
4. 用户的行为必须符合前一年状态，每一年必须受到之前经历的影响。
5. 必须同时考虑 choice（用户的选择）和 universe（外部条件）的共同作用。
6. 不要过度戏剧化，保持普通人的生活质感。
7. 每个文本字段用中文短句（不超过 80 字），具体、有画面感，不要空话。
8. decision 写用户这一年"主动做出的关键决定"；major_event 写"发生在这一年最重要的事"。
9. 最后给出五类 0-100 的内部评分（模型内部比较指标，不是客观测量）：
   career/finance/relationship/wellbeing 为"越高越好"，regret 为"后悔程度，越低越好"。

{feedback}

输出严格 JSON，格式如下（years 数组长度必须等于 {years}，year 字段填相对年数 1 到 {years}，不要写绝对年份）：

{{
  "summary": "（2-3 句话概述这条人生）",
  "years": [
    {{
      "year": 1,
      "career": "职业状态",
      "finance": "财务状态",
      "relationship": "关系状态",
      "location": "所在城市",
      "wellbeing": "身心状态",
      "major_event": "这一年最重要的事",
      "decision": "这一年你主动做出的关键决定"
    }}
  ],
  "features": {{
    "career_direction": "up 或 down 或 flat",
    "location_change": true 或 false,
    "startup": true 或 false,
    "job_switch": true 或 false,
    "relationship_change": true 或 false,
    "financial_direction": "up 或 down 或 flat",
    "wellbeing_direction": "up 或 down 或 flat",
    "main_theme": "（一个英文短语概括主题，如 high_income_high_pressure）"
  }},
  "final_scores": {{
    "career": 0-100,
    "finance": 0-100,
    "relationship": 0-100,
    "wellbeing": 0-100,
    "regret": 0-100
  }}
}}"""


def build_simulation_user(
    profile: str,
    choice_label: str,
    choice_text: str,
    universe: dict,
    years: int,
    start_year: int,
    feedback: str = "",
) -> str:
    if feedback:
        feedback = f"上一版本被质量检查指出以下问题，这一版必须修正：\n{feedback}"
    return SIMULATION_USER_V1.format(
        profile=profile,
        choice_label=choice_label,
        choice_text=choice_text,
        years=years,
        start_year=start_year,
        feedback=feedback,
        **{k: universe.get(k, "（未指定）") for k in (
            "macro_environment", "career_shock", "financial_shock",
            "relationship_shock", "opportunity", "random_event")},
    )
