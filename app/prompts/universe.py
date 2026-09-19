"""平行宇宙生成 Prompt（V1）。"""

UNIVERSE_SYSTEM_V1 = """[[task:universes]]
你正在为一个人生决策模拟系统生成"平行宇宙外部条件"。
你只负责描述外部世界会发生什么，绝不替用户做决定，也绝不预测用户的最终人生结果。
输出必须是严格的 JSON，不要输出任何 JSON 以外的文字。"""

UNIVERSE_USER_V1 = """用户背景：

{profile}

时间跨度：未来 {years} 年（从 {start_year} 年开始）。

请一次性生成 {n} 个彼此差异明显、但现实中合理的外部环境组合。

这一批宇宙的整体基调：{lean}（但每个宇宙内部仍要有自己的具体起伏）。

要求：

1. 不要替用户做决定。
2. 不要预测最终人生结果，不要提及用户会怎么选。
3. 只生成外部扰动和机会，不写用户的主观选择。
4. 每个宇宙必须包含以下六个字段，全部为中文短句（每个不超过 60 字）：
   - macro_environment：这 {years} 年的宏观环境/行业环境
   - career_shock：职业层面会遇到的冲击或变化
   - financial_shock：财务/市场层面的变化
   - relationship_shock：关系/家庭层面的变化或压力
   - opportunity：中间某一年出现的具体机会
   - random_event：一件影响较大的随机事件
5. 有好有坏：不允许全部极端正面，也不允许全部极端负面。
6. 保持现实合理性，不要科幻、不要夸张。
7. 各宇宙之间要真正不同（行业、节奏、事件类型都要拉开差距），不要换词重复。

输出严格 JSON，格式如下：

{{
  "universes": [
    {{
      "macro_environment": "...",
      "career_shock": "...",
      "financial_shock": "...",
      "relationship_shock": "...",
      "opportunity": "...",
      "random_event": "..."
    }}
  ]
}}"""


def build_universe_user(profile: str, years: int, n: int, start_year: int, lean: str) -> str:
    return UNIVERSE_USER_V1.format(profile=profile, years=years, n=n, start_year=start_year, lean=lean)
