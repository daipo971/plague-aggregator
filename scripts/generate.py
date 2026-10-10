"""
页面生成模块：生成首页 index.html、说明页 about.html 和 RSS（feed.xml）。

设计要点：
- 纯手写 HTML + 内联 CSS/JS，无外部依赖，手机友好、加载快
- 首页先给"一眼看懂"的概况和最新要闻，再按类别分栏
- 每条先显示一句话中文要点，详细摘要点开再看
- 支持按类别筛选和关键词搜索
- 未证实、争议说法单独栏目，并加醒目提示
"""

import html as html_lib
import logging
from datetime import datetime
from xml.sax.saxutils import escape

log = logging.getLogger("generate")

# 栏目定义：key -> (中文名, 配色, 一句话说明)
COLUMNS = [
    ("official", "官方机构", "#1a73e8", "各国政府与国际组织发布的通报"),
    ("professional", "专业机构", "#0d8043", "研究机构、学术期刊与专业媒体"),
    ("media", "媒体报道", "#b06000", "正规新闻媒体的报道"),
    ("unverified", "未证实信息", "#7b1fa2", "社交平台等渠道的说法，尚未得到证实"),
    ("controversial", "争议说法", "#c62828", "阴谋论或有争议的说法，缺乏可靠证据"),
]

# 未证实 / 争议栏目顶部的醒目提示
CAUTION_TYPES = {
    "unverified": "以下内容来自社交平台或未经证实的渠道，尚未得到官方或权威媒体确认，仅供参考。",
    "controversial": "以下内容属于争议说法或阴谋论，缺乏可靠证据，不代表本站观点。请勿据此改变就医或防疫行为。",
}

# 页面顶部固定医疗提示（通用公共卫生信息，覆盖所有传染病）
HEALTH_BANNER = (
    "本站聚合 WHO、各国疾控等官方与专业信源及媒体公开报道的全球传染病疫情信息，"
    "仅供参考，不提供诊疗建议。如出现发热、咳嗽、腹泻、皮疹等不适症状，请尽快就医，"
    "健康问题请以医生意见和官方指引为准。"
)

OFFICIAL_LINKS = [
    ("WHO 突发卫生事件（英文）", "https://www.who.int/emergencies"),
    ("美国 CDC 疫情动态（英文）", "https://www.cdc.gov/outbreaks.html"),
]

COMMON_CSS = """
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f5f6f8; color: #222; line-height: 1.6; }
  a { color: #1a73e8; }
  header { background: #14213d; color: #fff; padding: 20px 16px; }
  header h1 { margin: 0 0 6px; font-size: 1.3rem; }
  header p { margin: 0; opacity: .8; font-size: .85rem; }
  header nav a { color: #ffd54f; margin-right: 14px; font-size: .85rem; }
  .banner { background: #fff8e1; border-bottom: 2px solid #ffc107; padding: 12px 16px;
            font-size: .85rem; color: #5d4037; }
  main { max-width: 760px; margin: 0 auto; padding: 12px 12px 40px; }
  h2 { font-size: 1.05rem; margin: 22px 4px 10px; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
  .sec-desc { margin: -6px 4px 10px; font-size: .8rem; color: #666; }
  .card { background: #fff; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card[hidden] { display: none; }
  .card h3 { margin: 8px 0 4px; font-size: 1rem; }
  .card h3 a { color: #14213d; text-decoration: none; }
  .card h3 a:hover { text-decoration: underline; }
  .meta { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
          gap: 6px; font-size: .75rem; color: #888; }
  .tag { background: #eef2f7; color: #345; padding: 2px 8px; border-radius: 20px; }
  .disease-tag { background: #e8f5e9; color: #2e7d32; padding: 2px 8px; border-radius: 20px; margin-left: 6px; font-weight: 600; }
  .brief { margin: 4px 0 6px; font-size: .98rem; font-weight: 600; color: #1f2937; }
  .summary { margin: 6px 0 10px; font-size: .9rem; color: #444; }
  details.more { margin-top: 6px; }
  details.more > summary { cursor: pointer; color: #1a73e8; font-size: .85rem; }
  .medical-note { background: #fff3e0; border-left: 3px solid #ff9800; padding: 8px 10px;
                  font-size: .8rem; color: #6d4c00; margin: 8px 0; border-radius: 0 6px 6px 0; }
  .ai-badge { background: #e8f0fe; color: #1a73e8; font-size: .7rem; padding: 2px 8px;
              border-radius: 20px; margin-left: 6px; }
  .raw-badge { background: #f1f5f9; color: #64748b; font-size: .7rem; padding: 2px 8px;
               border-radius: 20px; margin-left: 6px; }
  .timeline { margin: 10px 0; padding: 10px 12px; background: #f8fafc; border-radius: 8px; font-size: .85rem; }
  .tl-title { font-weight: 700; margin-bottom: 6px; color: #334155; }
  .timeline ul { margin: 0; padding-left: 18px; color: #475569; }
  .timeline li { margin-bottom: 4px; }
  .treatment { margin: 10px 0; padding: 10px 12px; background: #ecfdf5;
               border-left: 3px solid #10b981; border-radius: 0 8px 8px 0; font-size: .85rem; }
  .tr-title { font-weight: 700; margin-bottom: 6px; color: #065f46; }
  .tr-sub { font-weight: 400; font-size: .75rem; color: #6b7280; }
  .treatment p { margin: 0; color: #374151; }
  .caution { margin: 0 4px 10px; padding: 8px 12px; background: #fdecea; color: #611a15;
             border-radius: 8px; font-size: .85rem; }
  .en-block { margin: 10px 0; font-size: .82rem; color: #555; }
  .en-block summary { cursor: pointer; color: #1a73e8; }
  .en-block p { margin: 6px 0 0; padding: 8px 10px; background: #f8fafc; border-radius: 6px; }
  .origin { font-size: .82rem; color: #1a73e8; text-decoration: none; }
  .overview { background: #fff; border-radius: 10px; padding: 14px 16px; margin-top: 12px;
              box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .overview h2 { margin: 0 0 6px; }
  .intro { margin: 0 0 12px; font-size: .85rem; color: #555; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .stat { background: #f8fafc; border-radius: 8px; padding: 8px; text-align: center; }
  .stat b { display: block; font-size: 1.3rem; }
  .stat span { font-size: .75rem; color: #666; }
  .stat.total { background: #14213d; }
  .stat.total b, .stat.total span { color: #fff; }
  .overview h3 { font-size: .95rem; margin: 16px 0 6px; }
  ol.latest { margin: 0; padding-left: 20px; font-size: .9rem; }
  ol.latest li { margin-bottom: 8px; }
  ol.latest a { color: #14213d; text-decoration: none; }
  ol.latest a:hover { text-decoration: underline; }
  .lt { display: block; font-size: .75rem; color: #888; }
  .controls { position: sticky; top: 0; z-index: 5; background: #f5f6f8; padding: 10px 0 6px; margin-top: 12px; }
  .controls input { width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px;
                    font-size: .95rem; background: #fff; }
  .filters { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .fbtn { border: 1px solid #cbd5e1; background: #fff; color: #334155; padding: 5px 12px;
          border-radius: 20px; font-size: .8rem; cursor: pointer; }
  .fbtn.active { background: #14213d; border-color: #14213d; color: #fff; }
  .empty { text-align: center; color: #999; padding: 20px; }
  .about p, .about li { font-size: .95rem; }
  .about .box { background: #fff; border-radius: 10px; padding: 14px 18px; margin-bottom: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  footer { text-align: center; font-size: .75rem; color: #999; padding: 20px; line-height: 1.8; }
  footer a { color: #1a73e8; }
  .author { background: #f1f5f9; color: #475569; font-size: .7rem; padding: 2px 8px;
            border-radius: 20px; margin-left: 6px; }
  .dgrid { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .dchip { border: 1px solid #cbd5e1; background: #fff; color: #334155; padding: 5px 12px;
           border-radius: 20px; font-size: .8rem; cursor: pointer; }
  .dchip b { color: #2e7d32; margin-left: 4px; }
  .dchip.active { background: #2e7d32; border-color: #2e7d32; color: #fff; }
  .dchip.active b { color: #fff; }
  .drow { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; align-items: center; }
  .dlabel { font-size: .8rem; color: #666; }
  .dbtn { border: 1px solid #bbf7d0; background: #f0fdf4; color: #166534; padding: 5px 12px;
          border-radius: 20px; font-size: .8rem; cursor: pointer; }
  .dbtn.active { background: #2e7d32; border-color: #2e7d32; color: #fff; }
"""


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


def brief_of(item: dict) -> str:
    """一句话要点：优先用 AI 生成的要点，没有则截取中文摘要。"""
    brief = (item.get("brief_zh") or "").strip()
    if brief:
        return brief
    summary = (item.get("summary_zh") or "").strip()
    return summary[:60] + ("…" if len(summary) > 60 else "")


def label_of(source_type: str) -> str:
    for key, label, _, _ in COLUMNS:
        if key == source_type:
            return label
    return source_type


def render_card(item: dict, tz_name: str) -> str:
    """渲染单条卡片：一句话要点 + 可展开的详细内容。"""
    title = item.get("title_zh", "")
    brief = brief_of(item)
    source = item.get("source_name", "")
    disease = item.get("disease_zh", "")
    search_text = " ".join([title, brief, source, disease]).lower()
    disease_badge = f'<span class="disease-tag">🦠 {esc(disease)}</span>' if disease and disease != "未明确" else ""
    author = (item.get("author") or "").strip()
    author_badge = f'<span class="author">👤 @{esc(author)}</span>' if author else ""

    if item.get("manual"):
        status_badge = '<span class="ai-badge">✍️ 人工整理</span>'
    elif item.get("ai_processed"):
        status_badge = '<span class="ai-badge">✨ AI 整理</span>'
    else:
        status_badge = '<span class="raw-badge">原文 · 未翻译</span>'

    medical_note = ""
    if item.get("medical_advice"):
        medical_note = (
            '<div class="medical-note">⚠️ 该条目涉及治疗/预防/就医建议，'
            "请以医生意见为准</div>"
        )

    timeline_html = ""
    timeline = item.get("timeline") or []
    if timeline:
        tl_items = "\n".join(f"<li>{esc(t)}</li>" for t in timeline)
        timeline_html = (
            '<div class="timeline"><div class="tl-title">🕐 事件时间线</div>'
            f"<ul>{tl_items}</ul></div>"
        )

    treatment_html = ""
    treatment = (item.get("treatment") or "").strip()
    if treatment:
        treatment_html = (
            '<div class="treatment"><div class="tr-title">💊 治疗与防控'
            '<span class="tr-sub">（据报道整理，非医疗建议）</span></div>'
            f"<p>{esc(treatment)}</p></div>"
        )

    en_html = ""
    summary_en = (item.get("summary_en") or "").strip()
    if summary_en:
        en_html = (
            '<details class="en-block"><summary>🇬🇧 English summary</summary>'
            f"<p>{esc(summary_en)}</p></details>"
        )

    summary_zh = item.get("summary_zh", "")
    url = esc(item.get("url", ""))
    return f"""
    <article class="card" data-cat="{esc(item.get('source_type', ''))}" data-disease="{esc(disease)}" data-search="{esc(search_text)}">
      <div class="meta">
        <span><span class="tag">{esc(source)}</span>{disease_badge}{author_badge}{status_badge}</span>
        <time>{esc(fmt_time(item.get('published', ''), tz_name))}</time>
      </div>
      <h3><a href="{url}" target="_blank" rel="noopener">{esc(title)}</a></h3>
      <p class="brief">{esc(brief)}</p>
      <details class="more">
        <summary>查看详细摘要</summary>
        <p class="summary">{esc(summary_zh)}</p>
        {timeline_html}
        {treatment_html}
        {en_html}
      </details>
      {medical_note}
      <a class="origin" href="{url}" target="_blank" rel="noopener">阅读原文 →</a>
    </article>"""


def render_overview(items: list, tz_name: str) -> str:
    """首页概况：各类数量 + 最新要闻，让人一眼看懂目前情况。"""
    counts = {key: 0 for key, _, _, _ in COLUMNS}
    for item in items:
        if item.get("source_type") in counts:
            counts[item["source_type"]] += 1

    chips = "".join(
        f'<div class="stat"><b style="color:{color}">{counts[key]}</b><span>{label}</span></div>'
        for key, label, color, _ in COLUMNS
    )
    # 疾病索引：按条数降序，只列已明确分类的疾病
    dcounts = {}
    for item in items:
        dz = (item.get("disease_zh") or "").strip()
        if dz and dz != "未明确":
            dcounts[dz] = dcounts.get(dz, 0) + 1
    dsorted = sorted(dcounts.items(), key=lambda x: -x[1])
    dchips = "".join(
        f'<button class="dchip" data-disease="{esc(dz)}">\U0001F9A0 {esc(dz)}<b>{n}</b></button>'
        for dz, n in dsorted
    )
    disease_html = (
        "<h3>\U0001F9A0 疾病分类</h3>"
        '<p class="intro">按疾病筛选浏览，点击进入：</p>'
        f'<div class="dgrid">{dchips or "<span>暂无分类</span>"}</div>'
    )
    # 最新要闻只放已经用中文整理好的条目，避免显示外文原标题
    translated = [i for i in items if i.get("ai_processed") and i.get("brief_zh")]
    latest = sorted(translated, key=lambda x: x.get("published", ""), reverse=True)[:5]
    latest_html = "".join(
        f'<li><a href="{esc(i.get("url", ""))}" target="_blank" rel="noopener">'
        f'{esc(brief_of(i))}</a>'
        f'<span class="lt">[{esc(label_of(i.get("source_type", "")))}] {esc(i.get("source_name", ""))}'
        f' · {esc(fmt_time(i.get("published", ""), tz_name))}</span></li>'
        for i in latest
    )
    return f"""
    <section class="overview">
      <h2>一眼看懂</h2>
      <p class="intro">本站每 30 分钟自动抓取全球公开信源，并用中文整理要点。目前收录情况如下：</p>
      <div class="stats">
        <div class="stat total"><b>{len(items)}</b><span>总条数</span></div>
        {chips}
      </div>
      {disease_html}
      <h3>最新要闻</h3>
      <ol class="latest">{latest_html or '<li>暂无内容</li>'}</ol>
    </section>"""


def render_controls(items: list) -> str:
    buttons = ['<button class="fbtn active" data-filter="all">全部</button>']
    for key, label, _, _ in COLUMNS:
        buttons.append(f'<button class="fbtn" data-filter="{key}">{label}</button>')
    dcounts = {}
    for item in items:
        dz = (item.get("disease_zh") or "").strip()
        if dz and dz != "未明确":
            dcounts[dz] = dcounts.get(dz, 0) + 1
    dsorted = sorted(dcounts.items(), key=lambda x: -x[1])
    dbuttons = ['<button class="dbtn active" data-dfilter="all">全部疾病</button>']
    for dz, n in dsorted:
        dbuttons.append(f'<button class="dbtn" data-dfilter="{esc(dz)}">{esc(dz)}({n})</button>')
    return f"""
    <div class="controls" id="controls">
      <input id="q" type="search" placeholder="搜索关键词，例如：伊尔库茨克、俄罗斯、疫苗" aria-label="搜索">
      <div class="filters">{''.join(buttons)}</div>
      <div class="drow"><span class="dlabel">\U0001F9A0 疾病：</span>{''.join(dbuttons)}</div>
      <p id="empty" class="empty" hidden>没有符合条件的内容。</p>
    </div>"""


def render_sections(items: list, tz_name: str) -> str:
    sections = []
    for key, label, color, desc in COLUMNS:
        cards = [i for i in items if i.get("source_type") == key]
        if not cards:
            continue
        caution = CAUTION_TYPES.get(key)
        caution_html = f'<p class="caution">⚠️ {esc(caution)}</p>' if caution else ""
        cards_html = "\n".join(render_card(i, tz_name) for i in cards)
        sections.append(f"""
    <section data-section="{key}">
      <h2><span class="dot" style="background:{color}"></span>{label}（{len(cards)}）</h2>
      <p class="sec-desc">{esc(desc)}</p>
      {caution_html}
      {cards_html}
    </section>""")
    return "".join(sections) or '<p class="empty">暂无内容，等待下次抓取…</p>'


FILTER_SCRIPT = """
<script>
(function () {
  var q = document.getElementById('q');
  var btns = document.querySelectorAll('.fbtn');
  var dbtns = document.querySelectorAll('.dbtn');
  var dchips = document.querySelectorAll('.dchip');
  var cards = document.querySelectorAll('.card');
  var secs = document.querySelectorAll('section[data-section]');
  var empty = document.getElementById('empty');
  var cat = 'all';
  var dis = 'all';
  function apply() {
    var kw = (q.value || '').trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (c) {
      var ok = (cat === 'all' || c.dataset.cat === cat) &&
               (dis === 'all' || c.dataset.disease === dis) &&
               (!kw || c.dataset.search.indexOf(kw) !== -1);
      c.hidden = !ok;
      if (ok) shown++;
    });
    secs.forEach(function (s) {
      s.hidden = !s.querySelector('.card:not([hidden])');
    });
    empty.hidden = shown > 0;
  }
  function setDisease(d) {
    dis = d;
    dbtns.forEach(function (x) { x.classList.toggle('active', x.dataset.dfilter === d); });
    dchips.forEach(function (x) { x.classList.toggle('active', x.dataset.disease === d); });
    apply();
  }
  btns.forEach(function (b) {
    b.addEventListener('click', function () {
      cat = b.dataset.filter;
      btns.forEach(function (x) { x.classList.toggle('active', x === b); });
      apply();
    });
  });
  dbtns.forEach(function (b) {
    b.addEventListener('click', function () { setDisease(b.dataset.dfilter); });
  });
  dchips.forEach(function (ch) {
    ch.addEventListener('click', function () {
      setDisease(ch.dataset.disease);
      document.getElementById('controls').scrollIntoView();
    });
  });
  q.addEventListener('input', apply);
})();
</script>
"""


def render_page(items: list, cfg: dict, updated_at: str) -> str:
    """生成首页。"""
    site = cfg.get("site", {})
    tz_name = site.get("timezone", "Asia/Taipei")
    title = site.get("title", "疫情信息聚合")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(site.get('description', ''))}">
<link rel="alternate" type="application/rss+xml" title="{esc(title)} RSS" href="feed.xml">
<style>{COMMON_CSS}</style>
</head>
<body>
<header>
  <h1>🦠 {esc(title)}</h1>
  <p>{esc(site.get('description', ''))}</p>
  <p>最后更新：{esc(updated_at)}（{esc(tz_name)}）</p>
  <nav><a href="about.html">关于本站与阅读说明</a><a href="feed.xml">RSS 订阅</a></nav>
</header>
<div class="banner">💊 {esc(HEALTH_BANNER)}</div>
<main>
{render_overview(items, tz_name)}
{render_controls(items)}
{render_sections(items, tz_name)}
</main>
<footer>
  内容来自公开信源，仅展示一句话要点、摘要与原文链接，不转载全文。<br>
  未证实与争议栏目的内容不代表本站观点。本站不提供诊疗建议，健康问题请咨询医生。<br>
  <a href="about.html">关于本站</a> · <a href="feed.xml">RSS</a>
</footer>
{FILTER_SCRIPT}
</body>
</html>"""


def render_about(cfg: dict, updated_at: str) -> str:
    """生成说明页：本站做什么、怎么分类、AI 的局限、如何阅读。"""
    site = cfg.get("site", {})
    title = site.get("title", "疫情信息聚合")
    column_items = "".join(
        f'<li><b style="color:{color}">{label}</b>：{desc}</li>'
        for _, label, color, desc in COLUMNS
    )
    links = "".join(f'<li><a href="{url}" target="_blank" rel="noopener">{name}</a></li>'
                    for name, url in OFFICIAL_LINKS)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关于本站 · {esc(title)}</title>
<meta name="description" content="本站如何收集信息、如何分类、AI 的作用与局限">
<style>{COMMON_CSS}</style>
</head>
<body>
<header>
  <h1>关于本站</h1>
  <p>{esc(title)} · 最后更新：{esc(updated_at)}</p>
  <nav><a href="index.html">← 返回首页</a><a href="feed.xml">RSS 订阅</a></nav>
</header>
<main class="about">
  <div class="box">
    <h2 style="margin-top:0">本站是什么</h2>
    <p>这是一个自动运行的信息聚合页面。它每 30 分钟从各类公开信源抓取最新内容，只保存标题、摘要和原文链接，并用中文整理出一句话要点，方便快速了解情况。</p>
    <p>本站不是新闻机构，也不对内容做事实核查。每条内容都会注明来源，请点击"阅读原文"自行核对。</p>
  </div>
  <div class="box">
    <h2 style="margin-top:0">栏目怎么分</h2>
    <ul>{column_items}</ul>
    <p>"未证实"与"争议说法"两个栏目单独放置，并在栏目顶部提示。请不要把这两个栏目的内容当作事实。</p>
  </div>
  <div class="box">
    <h2 style="margin-top:0">AI 做了什么，局限在哪里</h2>
    <ul>
      <li>把外文内容翻译成中文，并整理一句话要点和较完整的摘要。</li>
      <li>AI 可能出错或遗漏重点，所以每条都保留原文链接，以原文为准。</li>
      <li>标注"原文 · 未翻译"的条目，表示 AI 尚未处理，显示的是原文标题。</li>
      <li>涉及治疗、预防或就医的内容会加上提示，但这不构成医疗建议。</li>
    </ul>
  </div>
  <div class="box">
    <h2 style="margin-top:0">如何判断信息可靠性</h2>
    <ul>
      <li>优先看官方通报（如各国卫生部门、WHO）。</li>
      <li>同一事件看多方说法，注意是否有官方或权威媒体确认。</li>
      <li>看到涉及治疗、用药、防疫的说法，请以医生或官方指引为准，不要自行用药或改变就医行为。</li>
    </ul>
  </div>
  <div class="box">
    <h2 style="margin-top:0">权威参考资料</h2>
    <ul>{links}</ul>
  </div>
  <div class="box">
    <h2 style="margin-top:0">免责声明</h2>
    <p>本站内容仅供信息参考，不构成医疗、法律或其他专业建议。信息来源多样，准确性无法保证。</p>
  </div>
</main>
<footer><a href="index.html">返回首页</a> · <a href="feed.xml">RSS</a></footer>
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
<description>{escape(brief_of(item))}（来源：{escape(item.get('source_name', ''))}）</description>
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
    """写出 docs/index.html、docs/about.html 与 docs/feed.xml。"""
    from zoneinfo import ZoneInfo
    tz_name = cfg.get("site", {}).get("timezone", "Asia/Taipei")
    try:
        updated = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    with open(f"{docs_dir}/index.html", "w", encoding="utf-8") as f:
        f.write(render_page(items, cfg, updated))
    with open(f"{docs_dir}/about.html", "w", encoding="utf-8") as f:
        f.write(render_about(cfg, updated))
    with open(f"{docs_dir}/feed.xml", "w", encoding="utf-8") as f:
        f.write(render_rss(items, cfg))
    log.info("已生成页面：%d 条内容", len(items))
