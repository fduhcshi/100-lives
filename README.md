# 100 Lives · 100 个平行人生模拟器

把人生的选择题变成可以"运行"的实验：输入你的现状和两个选项（A / B），系统会
创建 N 个相同的平行世界，让每个世界里的你分别做出两种选择，模拟未来 1–10 年的
人生轨迹，然后告诉你——**在相同的世界条件下，两种选择分别走向了哪里**。

> ⚠️ 本项目是思想实验与叙事工具，不是预测系统。所有输出由大模型生成，
> 展示的是"N 个模拟世界中的分布"，**不是概率**，更不是命运。

## 核心设计

- **共享宇宙配对比较**：宇宙 i 中的你既会经历 A 也会经历 B（宏观环境、行业
  冲击、随机事件完全一致），因此对比的是"同一起点下的选择差异"，而不是
  两组不可比样本。
- **质量检查（Critic）**：每条轨迹生成后由独立评审打分（一致性 / 现实感 /
  因果连贯 / 多样性），不通过的轨迹会带着问题清单重新生成，最多重试 2 次。
- **只展示世界数，不展示概率**：界面和报告中的结论一律是
  "X / N 个模拟世界"，频率 ≠ 概率，避免给出虚假的确定性。
- **可以和未来的你聊天**：选中任意一条轨迹，以轨迹终点年份的"你"的口吻
  对话，了解那条人生路的细节。

## 快速开始

需要 Python 3.11+。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 LLM（三选一）
#    a) 复制 .env.example 为 .env，填入你的 Anthropic Messages 兼容网关：
#         LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
#    b) 不建 .env：程序自动回退读取本机已设置的
#         ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / ANTHROPIC_MODEL
#    c) 离线试用（内置 Mock，输出为模板内容，不需要任何密钥）：
cp .env.example .env   # 然后编辑，或直接跳到第 3 步用 --mock

# 3. 启动
python run.py            # http://127.0.0.1:8000
python run.py --mock     # 离线 Mock 模式
python run.py --port 8017
```

打开浏览器访问 <http://127.0.0.1:8000>，填写现状描述和两个选择即可开始。

## 配置项

| 环境变量 | 说明 | 默认 |
|---|---|---|
| `LLM_BASE_URL` | Anthropic Messages 兼容网关地址（`/v1/messages` 可省略） | 回退 `ANTHROPIC_BASE_URL` |
| `LLM_API_KEY` | 网关密钥（只保存在本地 `.env`，已被 .gitignore 排除） | 回退 `ANTHROPIC_API_KEY` |
| `LLM_MODEL` | 模型名 | 回退 `ANTHROPIC_MODEL` |
| `LLM_MOCK` | `1` 时强制离线 Mock | 关 |
| `MAX_CONCURRENCY` | 并发 LLM 请求数上限 | 20 |
| `HOST` / `PORT` | 监听地址 | `127.0.0.1:8000` |

## 运行流程

```
提交请求 → 创建 N 个平行世界 → 并发模拟 A/B（内含 Critic 检查与重生成）
        → 各自聚类 → 配对比较（Δ = Score(Aᵢ) − Score(Bᵢ)）→ 洞察报告 → 落盘
```

- 进度通过 `GET /api/status/{run_id}` 轮询：`universes → simulation →
  clustering → comparison → summary → done / failed`。
- 每次运行完整保存为 `data/runs/{run_id}.json`，同时生成可直接打开的
  `data/runs/{run_id}.html` 单文件报告；刷新页面或重启服务后仍可通过
  `/result/{run_id}` 查看。离线 HTML 可浏览完整报告，未来自己对话仍需启动后端。
- 部分轨迹生成失败时会自动降级（只统计成功配对的世界数），并在报告中说明。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/simulate` | 提交模拟（202，后台执行） |
| GET | `/api/status/{run_id}` | 进度与阶段 |
| GET | `/api/result/{run_id}` | 完整结果 JSON |
| GET | `/api/result/{run_id}/html` | 下载单文件 HTML 报告 |
| POST | `/api/future-self-chat` | 与某条轨迹的"未来的你"对话 |
| GET | `/api/health` | 健康检查（含 LLM 是否已配置） |

## 测试

结果页为单页连续报告：A/B 总览、偏好调节、世界矩阵、双人生路线与详细分析统一展示，无模式切换或章节翻页。世界矩阵按实际生成的世界展示 A/B 配对，分差不超过 3 分标记为接近；缺失数据单独计数。偏好滑块只在浏览器中重新加权已有结果（后悔反向计分），同步更新总览和世界矩阵，不调用 LLM，刷新后恢复等权。人生路线可逐年展开。下载按钮右侧的「分享海报」可预览并保存 PNG，包含当前偏好；HTML 报告打开时仍默认等权。已有结果无需重新模拟，刷新结果页即可体验。

前端计分与配对逻辑测试：`node tests/result_story.test.cjs`。

```bash
pip install -r requirements-dev.txt
pytest            # 47 个用例，全部离线运行（Mock LLM），约 2 秒
```

## 目录结构

```
app/
  main.py               FastAPI 入口与路由
  config.py             配置（只从环境变量 / .env 读取）
  models/               Pydantic 数据结构（请求 / 轨迹 / 结果）
  prompts/              全部 LLM 提示词（带版本号，集中管理）
  services/             LLM 适配器、宇宙生成、模拟、Critic、聚类、
                        汇总、流水线编排、运行存储、未来对话
  utils/                JSON 解析、重试、日志
static/                 原生 HTML / CSS / JS 前端（无构建步骤）
tests/                  pytest 测试套件（离线）
data/runs/              运行结果（JSON，已 gitignore）
run.py                  启动脚本
```

## 边界与免责声明

- 本地单人工具：无数据库、无登录、无搜索，数据只存在本机 `data/runs/`。
- 模拟次数有限（默认每选择最多 100 个世界）：小样本下的"X / N"不具备
  统计显著性，请当作发散思考的素材，而不是决策依据。
- 模型可能生成偏颇或不符合你实际情况的叙事，请保持批判性阅读。

## Star History

<!-- 上传前请把本段中所有 YOUR_GITHUB_USERNAME/100-lives 替换成你的真实仓库路径 -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=YOUR_GITHUB_USERNAME/100-lives&type=Date&theme=dark" />
  <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=YOUR_GITHUB_USERNAME/100-lives&type=Date" />
  <a href="https://star-history.com/#YOUR_GITHUB_USERNAME/100-lives&Date">
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=YOUR_GITHUB_USERNAME/100-lives&type=Date" />
  </a>
</picture>
