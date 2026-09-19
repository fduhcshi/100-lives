"""轨迹质量检查（Critic）Prompt（V1）。"""

CRITIC_SYSTEM_V1 = """[[task:critic]]
你是一个严格的人生模拟轨迹质量检查员。你检查轨迹的内部逻辑与真实感，不做人生价值判断。
输出必须是严格的 JSON，不要输出任何 JSON 以外的文字。"""

CRITIC_USER_V1 = """请检查以下模拟人生轨迹。

用户背景：

{profile}

用户的决策：选择 {choice_label}：{choice_text}

该轨迹所处宇宙的外部条件：

{universe}

待检查的轨迹：

{trajectory}

请从以下四个方面打分（每项 0-100）：

1. consistency（一致性）：年份之间是否有因果连续性，行为是否符合前一年状态。
2. realism（真实感）：是否像普通人的现实生活，有没有无解释的跃迁。
3. coherence（连贯性）：轨迹是否充分利用了 choice 与 universe 的共同作用，还是两者脱节。
4. diversity（独特性）：这条轨迹是否落入了"所有结果都很好/都很差"的模板，还是呈现了起伏。

如果存在以下问题，必须在 problems 数组中具体指出（每条一句话）：

- 无解释的财富跳跃或职位飞跃
- 前后城市/状态矛盾
- 年份时间矛盾
- 重大事件在后续年份没有影响
- 全程过度乐观或全程过度悲观
- 轨迹内容与用户背景、选择或宇宙条件无关

只要存在任一严重问题，或 realism < 60，或 consistency < 60，就应给出 accepted: false。

输出严格 JSON，格式如下：

{{
  "consistency": 0-100,
  "realism": 0-100,
  "coherence": 0-100,
  "diversity": 0-100,
  "accepted": true 或 false,
  "problems": ["问题1", "问题2"]
}}"""


def build_critic_user(
    profile: str, choice_label: str, choice_text: str, universe_brief: str, trajectory_json: str
) -> str:
    return CRITIC_USER_V1.format(
        profile=profile,
        choice_label=choice_label,
        choice_text=choice_text,
        universe=universe_brief,
        trajectory=trajectory_json,
    )
