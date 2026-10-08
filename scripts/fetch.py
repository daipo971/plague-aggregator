"""
抓取模块：读取 sources.yaml，逐个抓取信源，输出标准化条目。

支持两种信源：
- RSS（默认）：feedparser 解析
- kind: x_search：X（推特）搜索 API，需要环境变量 X_BEARER_TOKEN（付费 API，没有则跳过）

设计要点：
- 每个信源独立 try/except，一个源挂了不影响其他源
- 按链接去重（processed.json 里记过的不再返回）
- 只保留 keep_days 天内、且与鼠疫/疫情相关关键词匹配的内容
"""

import hashlib
import html
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import yaml

log = logging.getLogger("fetch")

# 允许的信源类型
# official / professional / media：主栏目
# unverified：未证实（社交平台等），单独栏目
# controversial：争议说法（阴谋论等），单独栏目
ALLOWED_TYPES = {"official", "professional", "media", "unverified", "controversial"}

# 相关性关键词：标题或摘要里必须至少出现一个，否则视为无关内容丢弃
RELEVANCE_RE = re.compile(
    r"plague|pneumonic|bubonic|yersinia|鼠疫|耶尔森|瘟疫|peste|чума|pesta",
    re.IGNORECASE,
)

X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


def strip_html(text: str) -> str:
    """去掉摘要里的 HTML 标签，只留纯文本。"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_title(text: str) -> str:
    """清理标题：去掉网址、话题标签（#xxx）和多余符号。"""
    text = re.sub(r"https?://\S+", " ", text or "")
    text = re.sub(r"#\S+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -|·:：")


def is_relevant(title: str, summary: str) -> bool:
    return bool(RELEVANCE_RE.search(f"{title} {summary}"))


def parse_time(entry) -> str:
    """把 RSS 里各种时间格式统一成 ISO 字符串，拿不到就用现在。"""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def make_item(source: dict, title: str, link: str, summary: str, published: str) -> dict:
    return {
        "title": clean_title(strip_html(title))[:200],
        "link": link,
        # 用链接的 md5 当稳定 id，用于去重
        "id": hashlib.md5(link.encode("utf-8")).hexdigest(),
        "summary_raw": strip_html(summary)[:500],
        "published": published,
        "source_name": source.get("name", "未知来源"),
        "source_type": source.get("type", ""),
    }


def fetch_rss(source: dict, max_items: int, cutoff: datetime) -> list:
    url = source.get("rss", "")
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:max_items]:
        link = (entry.get("link") or "").strip()
        if not link:
            continue
        published = parse_time(entry)
        try:
            if datetime.fromisoformat(published) < cutoff:
                continue  # 太旧的内容不要
        except Exception:
            pass
        title = strip_html(entry.get("title", ""))
        summary = entry.get("summary", "") or entry.get("description", "")
        if not is_relevant(title, strip_html(summary)):
            continue  # 与鼠疫/疫情无关
        items.append(make_item(source, title, link, summary, published))
    return items


def fetch_x_search(source: dict, max_items: int, cutoff: datetime) -> list:
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        log.info("信源 [%s] 需要 X_BEARER_TOKEN，未配置，已跳过", source.get("name"))
        return []
    params = {
        "query": source.get("query", ""),
        "max_results": min(max(max_items, 10), 100),
        "tweet.fields": "created_at,author_id",
        "expansions": "author_id",
        "user.fields": "username",
    }
    resp = requests.get(
        X_SEARCH_URL,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    users = {u["id"]: u.get("username", "") for u in data.get("includes", {}).get("users", [])}
    items = []
    for tw in data.get("data", []):
        text = tw.get("text", "")
        if not is_relevant(text, ""):
            continue
        username = users.get(tw.get("author_id", ""), "")
        link = f"https://x.com/{username or 'i'}/status/{tw['id']}"
        published = tw.get("created_at") or datetime.now(timezone.utc).isoformat()
        try:
            if datetime.fromisoformat(published.replace("Z", "+00:00")) < cutoff:
                continue
        except Exception:
            pass
        items.append(make_item(source, text[:120], link, text, published))
    return items


def fetch_one(source: dict, max_items: int, keep_days: int) -> list:
    """抓取单个信源，返回标准化条目列表。失败返回空列表并记日志。"""
    name = source.get("name", "未知来源")
    stype = source.get("type", "")
    if stype not in ALLOWED_TYPES:
        log.warning("信源 [%s] 的 type=%r 不在允许范围内，已跳过", name, stype)
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    try:
        if source.get("kind") == "x_search":
            items = fetch_x_search(source, max_items, cutoff)
        else:
            items = fetch_rss(source, max_items, cutoff)
    except Exception as e:  # noqa: BLE001 - 单个源失败只记日志
        log.warning("抓取信源 [%s] 失败：%s", name, e)
        return []
    log.info("信源 [%s] 抓到相关内容 %d 条", name, len(items))
    return items


def fetch_all(sources_path: str, processed_path: str, cfg: dict) -> list:
    """
    抓取全部启用的信源，返回「本次新出现的」条目。
    去重依据：processed.json 里记录过的链接 id。
    """
    with open(sources_path, encoding="utf-8") as f:
        sources = yaml.safe_load(f).get("sources", [])

    # 读已处理记录
    try:
        with open(processed_path, encoding="utf-8") as f:
            processed = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        processed = {"seen_ids": [], "ai_cache": {}}
    seen = set(processed.get("seen_ids", []))

    site_cfg = cfg.get("site", {})
    new_items = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        if src.get("kind") != "x_search" and not src.get("rss"):
            log.warning("信源 [%s] 没有填写 rss 地址，已跳过", src.get("name"))
            continue
        for item in fetch_one(src, site_cfg.get("max_items_per_source", 20),
                              site_cfg.get("keep_days", 30)):
            if item["id"] not in seen:
                new_items.append(item)

    # 按发布时间倒序
    new_items.sort(key=lambda x: x["published"], reverse=True)
    log.info("本次共发现 %d 条新内容", len(new_items))
    return new_items, processed
