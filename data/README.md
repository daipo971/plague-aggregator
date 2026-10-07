# 全球鼠疫 / 疫情信息聚合站

纯静态网站：GitHub Actions 每 30 分钟抓取一次，生成静态页面，托管在 GitHub Pages。
**只收录官方、专业、正规媒体三类信源**（WHO、CIDRAP、CDC 期刊、Google 新闻），不收录未证实的社交传言。

## 目录结构

```
.
├── config.yaml                  # 站点与 AI 配置（换模型、调参数改这里）
├── sources.yaml                 # 信源配置（增删 RSS 改这里）
├── requirements.txt             # Python 依赖
├── DEPLOY.md                    # 部署说明（从零上线看这份）
├── scripts/
│   ├── run.py                   # 总入口：抓取 -> AI -> 生成
│   ├── fetch.py                 # RSS 抓取 + 按链接去重
│   ├── ai_processor.py          # AI 处理模块（可切换模型，Key 走环境变量）
│   └── generate.py              # 生成 index.html + feed.xml
├── data/
│   └── processed.json           # 去重表 + AI 缓存（自动维护）
├── docs/                        # 生成的网站（index.html + feed.xml，GitHub Pages 直接托管）
└── .github/workflows/update.yml # 定时任务：每 30 分钟运行一次
```

## 本地运行

```bash
pip install -r requirements.txt

# 不调 AI 先跑通（config.yaml 里 ai.enabled 设为 false）
python scripts/run.py

# 要用 AI：设置环境变量（Key 绝不写进代码）
export AI_API_KEY="你的key"
python scripts/run.py

# 生成的页面在 docs/index.html，用浏览器打开即可预览
```

## 换 AI 模型

改 `config.yaml` 的 `ai.provider`：

- `openai_compatible`：OpenAI / DeepSeek / 通义千问等兼容接口，填 `base_url` 和 `model`
- `anthropic`：Anthropic 官方接口，填 `model`

要接新的模型商：在 `scripts/ai_processor.py` 里照着写一个 `AIProvider` 子类，
再在 `get_provider()` 里加一行分支即可。

## 增删信源

改 `sources.yaml`：加一段 `- name / type / rss / enabled` 就行。
`type` 只能填 `official` / `professional` / `media` 三类。
单个源挂了只记日志，不影响其他源。
