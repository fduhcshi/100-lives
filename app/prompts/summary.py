"""汇总类 Prompt（V1）：配对世界叙述 + 最终洞察报告。"""

MATCHED_NARRATIVE_SYSTEM_V1 = """[[task:matched]]
你在为人生决策模拟系统撰写"相同世界、不同选择"的对比叙述。
给定同一外部条件下两条轨迹的差异，用简洁、具体、有画面感的中文写出对比。
禁止把模拟结果表述为现实概率。输出必须是严格的 JSON。"""

MATCHED_NARRATIVE_USER_V1 = """用户背景：

{profile}

用户在纠结两个选择：

- 选择 A：{choice_a}
- 选择 B：{choice_b}

下面是 {n} 个平行宇宙中，差异最大的几个宇宙里两种选择的走向（每个宇宙同时模拟了 A 和 B，外部条件完全相同）：

{pairs}

请挑出最有洞察的 2-3 个宇宙，为每个宇宙写一条对比叙述：

- title：一句话点出这个宇宙里"真正的分岔点"是什么
- narrative：2-3 句话对比描述，例如"同样面对行业下行，A 的你如何如何；B 的你如何如何"。

最后给出 divergence_insight：根据这些配对对比，1-2 句话回答"真正造成结果差异的因素是什么"。

输出严格 JSON：

{{
  "examples": [
    {{
      "universe_id": 3,
      "title": "同样面对行业下行时",
      "narrative": "选择 A 的你……；选择 B 的你……"
    }}
  ],
  "divergence_insight": "..."
}}"""


INSIGHT_SYSTEM_V1 = """[[task:insight]]
你是一个谨慎的人生决策分析器。你基于大量模拟轨迹做结构性分析，但绝不假装能预测现实。
禁止把模拟结果表达成现实概率；禁止简单粗暴地推荐 A 或 B。输出必须是严格的 JSON。"""

INSIGHT_USER_V1 = """用户背景：

{profile}

用户在纠结两个选择：

- 选择 A：{choice_a}
- 选择 B：{choice_b}

每个选择各模拟了 {n} 条平行人生，两个选择共享同一批外部世界。以下是聚类汇总与配对比较结果：

【选择 A 的人生类型】

{summary_a}

【选择 B 的人生类型】

{summary_b}

【相同世界下的配对比较（A_i 与 B_i 共享同一宇宙）】

{matched}

请基于以上材料回答以下 7 个问题（每个答案 2-4 句话，要具体、要引用材料里的模式，不要空泛）：

1. structural_difference：两个选择最主要的结构性区别是什么？
2. deciding_factors：哪些因素真正决定了结果的好与坏？
3. unimportant_factors：哪些因素在多数世界里其实都不重要？
4. who_fits_a：什么价值观/偏好/处境的用户更适合选择 A？
5. who_fits_b：什么价值观/偏好/处境的用户更适合选择 B？
6. biggest_risk：两个选择共同的最大风险是什么？
7. info_to_confirm：用户最值得在决定前进一步确认的真实信息是什么？

输出严格 JSON：

{{
  "structural_difference": "...",
  "deciding_factors": "...",
  "unimportant_factors": "...",
  "who_fits_a": "...",
  "who_fits_b": "...",
  "biggest_risk": "...",
  "info_to_confirm": "..."
}}"""


def build_matched_user(profile: str, choice_a: str, choice_b: str, pairs_text: str, n: int) -> str:
    return MATCHED_NARRATIVE_USER_V1.format(
        profile=profile, choice_a=choice_a, choice_b=choice_b, pairs=pairs_text, n=n
    )


def build_insight_user(
    profile: str, choice_a: str, choice_b: str, n: int, summary_a: str, summary_b: str, matched: str
) -> str:
    return INSIGHT_USER_V1.format(
        profile=profile,
        choice_a=choice_a,
        choice_b=choice_b,
        n=n,
        summary_a=summary_a,
        summary_b=summary_b,
        matched=matched,
    )
