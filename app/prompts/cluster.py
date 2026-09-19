"""轨迹聚类 Prompt（V1）：把同一选择下的所有轨迹归纳成几类典型人生路径。"""

CLUSTER_SYSTEM_V1 = """[[task:cluster]]
你是一个人生轨迹聚类分析器。你把多条模拟人生轨迹归纳成少数几类"典型人生路径"。
每条轨迹必须且只能属于一个类别。输出必须是严格的 JSON，不要输出任何 JSON 以外的文字。"""

CLUSTER_USER_V1 = """用户正在比较两个人生选择，下面是选择 {choice_label}（{choice_text}）在 {n} 个平行世界中的模拟人生轨迹。

每行格式为：轨迹ID｜特征标签｜评分（职业/财务/关系/满意度/后悔）｜概述

{trajectories}

请把这些轨迹归纳成 {k} 类左右（可上下浮动 1 类）彼此明显不同的典型人生路径。

每一类输出：

- name：类别名（中文短语，如"高收入高压力线"、"换城市后回流"、"职业倦怠"）
- description：这类人生的概述（2 句话）
- trajectory_ids：属于这一类的所有轨迹 ID
- common_pattern：这一类的共同模式（1-2 句话）
- key_risk：这一类路径的主要风险（1 句话）
- key_opportunity：这一类路径的关键机会（1 句话）
- representative_trajectory_id：这一类中最有代表性的一条轨迹 ID

另外请给出：

- most_typical_trajectory_id：全部轨迹中最"典型"（最接近整体中位画像）的一条
- most_surprising_trajectory_id：全部轨迹中最意外、最不寻常但仍然合理的一条
- common_risks：这一选择下反复出现的风险（3-5 条，每条一句话）
- common_opportunities：这一选择下反复出现的机会（3-5 条，每条一句话）

注意：所有 ID 必须来自上面列表中真实存在的 ID；每条轨迹恰好归入一类，不允许遗漏或重复。

输出严格 JSON，格式如下：

{{
  "clusters": [
    {{
      "name": "...",
      "description": "...",
      "trajectory_ids": ["a_u01"],
      "common_pattern": "...",
      "key_risk": "...",
      "key_opportunity": "...",
      "representative_trajectory_id": "a_u01"
    }}
  ],
  "most_typical_trajectory_id": "...",
  "most_surprising_trajectory_id": "...",
  "common_risks": ["..."],
  "common_opportunities": ["..."]
}}"""


def build_cluster_user(choice_label: str, choice_text: str, trajectory_lines: list[str]) -> str:
    n = len(trajectory_lines)
    k = max(2, min(6, round(n / 4) + 1)) if n >= 12 else max(2, (n + 1) // 3)
    return CLUSTER_USER_V1.format(
        choice_label=choice_label,
        choice_text=choice_text,
        n=n,
        k=k,
        trajectories="\n".join(trajectory_lines),
    )
