"""
页面生成模块：把处理好的条目生成静态 index.html 和 feed.xml（RSS）。

设计要点：
- 纯手写 HTML+内联 CSS，无外部依赖，手机友好、加载快
- 按来源类型分栏目：官方 / 专业 / 媒体
- 只展示标题、摘要、链接，不转载全文
"""

import html as html_lib
import logging
from datetime import datetime
from xml.sax.saxutils import escape

log = logging.getLogger("generate")

# 栏目定义：key -> (中文名, 配色)
COLUMNS = [
    ("official", "官方机构", "#1a73e8"),
    ("professional", "专业机构", "#0d8043"),
    ("media", "媒体报道", "#b06000"),
]

# 页面顶部固定医疗提示（通用公共卫生信息）
HEALTH_BANNER = (
    "鼠疫是由鼠疫耶尔森菌引起的细菌性传染病，早期使用抗生素治疗效果好。"
    "如出现发烧、淋巴结肿痛、咳嗽咯血等症状，请尽快就医。本站仅聚合公开信息，"
    "不提供诊疗建议，健康问题请以医生意见为准。"
)


def esc(text: str) -> str:
    """转义 HTML 特殊字符，防止注入破坏页面。"""
    return html_lib.escape(text or "", quote=True)


def fmt_time(iso_str: str, tz_name: str) -> str:
    """ISO 时间转成站点时区的友好显示。"""
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return (iso_str or "")[:16].replace("T", " ")


def render_card(item: dict, tz_name: str) -> str:
    """渲染单条信息卡片：中文摘要 + 时间线 + 治疗方法 + 英文摘要（折叠）。"""
    medical_note = ""
    if item.get("medical_advice"):
        medical_note = (
            '<div class="medical-note">⚠️ 该条目涉及治疗/预防/就医建议，'
            "请以医生意见为准</div>"
        )
    relevant_note = ""
    if item.get("ai_processed") and not item.get("relevant", True):
        relevant_note = (
            '<div class="relevant-note">⚠️ AI 判断该报道可能与疫情无关，仅供参考</div>'
        )
    ai_badge = (
        '<span class="ai-badge">✨ AI 整理</span>' if item.get("ai_processed") else ""
    )

    timeline_html = ""
    timeline = item.get("timeline") or []
    if timeline:
        tl_items = "\n".join(f"<li>{esc(t)}</li>" for t in timeline)
        timeline_html = f"""
      <div class="timeline">
        <div class="tl-title">🕐 事件时间线</div>
        <ul>{tl_items}</ul>
      </div>"""

    treatment_html = ""
    treatment = (item.get("treatment") or "").strip()
    if treatment:
        treatment_html = f"""
      <div class="treatment">
        <div class="tr-title">💊 治疗与防控<span class="tr-sub">（据报道整理，非医疗建议）</span></div>
        <p>{esc(treatment)}</p>
      </div>"""

    en_html = ""
    summary_en = (item.get("summary_en") or "").strip()
    if summary_en:
        en_html = f"""
      <details class="en-block">
        <summary>🇬🇧 English summary</summary>
        <p>{esc(summary_en)}</p>
      </details>"""

    return f"""
    <article class="card">
      <div class="meta">
        <span><span class="tag">{esc(item.get('source_name', ''))}</span> {ai_badge}</span>
        <time>{esc(fmt_time(item.get('published', ''), tz_name))}</time>
      </div>
      <h3><a href="{esc(item.get('url', ''))}" target="_blank" rel="noopener">{esc(item.get('title_zh', ''))}</a></h3>
      <p class="summary">{esc(item.get('summary_zh', ''))}</p>
      {timeline_html}
      {treatment_html}
      {en_html}
      {relevant_note}
      {medical_note}
      <a class="origin" href="{esc(item.get('url', ''))}" target="_blank" rel="noopener">阅读原文 →</a>
    </article>"""


def render_page(items: list, cfg: dict, updated_at: str) -> str:
    """生成完整 HTML 页面。"""
    site = cfg.get("site", {})
    tz_name = site.get("timezone", "Asia/Taipei")
    title = site.get("title", "疫情信息聚合")

    sections = []
    for key, label, color in COLUMNS:
        cards = [i for i in items if i.get("source_type") == key]
        if not cards:
            continue
        cards_html = "\n".join(render_card(i, tz_name) for i in cards)
        sections.append(f"""
    <section>
      <h2><span class="dot" style="background:{color}"></span>{label}（{len(cards)}）</h2>
      {cards_html}
    </section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(site.get('description', ''))}">
<link rel="alternate" type="application/rss+xml" title="{esc(title)} RSS" href="feed.xml">
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 0; background: #f5f6f8; color: #222; line-height: 1.6; }}
  header {{ background: #14213d; color: #fff; padding: 20px 16px; }}
  header h1 {{ margin: 0 0 6px; font-size: 1.3rem; }}
  header p {{ margin: 0; opacity: .75; font-size: .85rem; }}
  .banner {{ background: #fff8e1; border-bottom: 2px solid #ffc107; padding: 12px 16px;
             font-size: .85rem; color: #5d4037; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 12px 12px 40px; }}
  section h2 {{ font-size: 1.05rem; margin: 22px 4px 10px; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .card h3 {{ margin: 8px 0; font-size: 1rem; }}
  .card h3 a {{ color: #14213d; text-decoration: none; }}
  .card h3 a:hover {{ text-decoration: underline; }}
  .meta {{ display: flex; justify-content: space-between; align-items: center; font-size: .75rem; color: #888; }}
  .tag {{ background: #eef2f7; color: #345; padding: 2px 8px; border-radius: 20px; }}
  .summary {{ margin: 6px 0 10px; font-size: .9rem; color: #444; }}
  .medical-note {{ background: #fff3e0; border-left: 3px solid #ff9800; padding: 8px 10px;
                   font-size: .8rem; color: #6d4c00; margin: 8px 0; border-radius: 0 6px 6px 0; }}
  .relevant-note {{ background: #f3e5f5; border-left: 3px solid #9c27b0; padding: 8px 10px;
                   font-size: .8rem; color: #4a148c; margin: 8px 0; border-radius: 0 6px 6px 0; }}
  .ai-badge {{ background: #e8f0fe; color: #1a73e8; font-size: .7rem; padding: 2px 8px;
               border-radius: 20px; margin-left: 6px; }}
  .timeline {{ margin: 10px 0; padding: 10px 12px; background: #f8fafc;
               border-radius: 8px; font-size: .85rem; }}
  .tl-title {{ font-weight: 700; margin-bottom: 6px; color: #334155; }}
  .timeline ul {{ margin: 0; padding-left: 18px; color: #475569; }}
  .timeline li {{ margin-bottom: 4px; }}
  .treatment {{ margin: 10px 0; padding: 10px 12px; background: #ecfdf5;
                border-left: 3px solid #10b981; border-radius: 0 8px 8px 0; font-size: .85rem; }}
  .tr-title {{ font-weight: 700; margin-bottom: 6px; color: #065f46; }}
  .tr-sub {{ font-weight: 400; font-size: .75rem; color: #6b7280; }}
  .treatment p {{ margin: 0; color: #374151; }}
  .en-block {{ margin: 10px 0; font-size: .82rem; color: #555; }}
  .en-block summary {{ cursor: pointer; color: #1a73e8; }}
  .en-block p {{ margin: 6px 0 0; padding: 8px 10px; background: #f8fafc; border-radius: 6px; }}
  .origin {{ font-size: .82rem; color: #1a73e8; text-decoration: none; }}
  footer {{ text-align: center; font-size: .75rem; color: #999; padding: 20px; }}
  footer a {{ color: #1a73e8; }}
</style>
</head>
<body>
<header>
  <h1>🦠 {esc(title)}</h1>
  <p>{esc(site.get('description', ''))}</p>
  <p>更新于 {esc(updated_at)} · <a href="feed.xml" style="color:#ffd54f">RSS 订阅</a></p>
</header>
<div class="banner">💊 {esc(HEALTH_BANNER)}</div>
<main>
{''.join(sections) if sections else '<p style="text-align:center;color:#999">暂无内容，等待下次抓取…</p>'}
</main>
<footer>
  内容来自公开信源，仅展示标题、摘要与原文链接，不转载全文。<br>
  本站不提供诊疗建议，健康问题请咨询医生。
</footer>
</body>
</html>"""


def render_rss(items: list, cfg: dict) -> str:
    """生成 RSS 2.0 订阅文件。"""
    site = cfg.get("site", {})
    base = site.get("base_url", "").rstrip("/")
    title = site.get("title", "")
    now = datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")

    rss_items = []
    for item in items[:50]:  # RSS 只放最新 50 条
        rss_items.append(f"""<item>
<title>{escape(item.get('title_zh', ''))}</title>
<link>{escape(item.get('url', ''))}</link>
<guid>{escape(item.get('url', ''))}</guid>
<pubDate>{escape(item.get('published', ''))}</pubDate>
<description>{escape(item.get('summary_zh', ''))}（来源：{escape(item.get('source_name', ''))}）</description>
</item>""")

    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
<channel>
<title>{escape(title)}</title>
<link>{escape(base)}</link>
<description>{escape(site.get('description', ''))}</description>
<lastBuildDate>{now}</lastBuildDate>
{''.join(rss_items)}
</channel>
</rss>"""


def generate(items: list, cfg: dict, docs_dir: str):
    """写出 docs/index.html 与 docs/feed.xml。"""
    from zoneinfo import ZoneInfo
    tz_name = cfg.get("site", {}).get("timezone", "Asia/Taipei")
    try:
        updated = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    with open(f"{docs_dir}/index.html", "w", encoding="utf-8") as f:
        f.write(render_page(items, cfg, updated))
    with open(f"{docs_dir}/feed.xml", "w", encoding="utf-8") as f:
        f.write(render_rss(items, cfg))
    log.info("已生成页面：%d 条内容", len(items))
