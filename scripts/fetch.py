"""
抓取模块：读取 sources.yaml，逐个抓取 RSS，输出标准化条目。

设计要点：
- 每个信源独立 try/except，一个源挂了不影响其他源
- 按链接去重（processed.json 里记过的不再返回）
- 只保留 keep_days 天内的内容
"""

import hashlib
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import yaml

log = logging.getLogger("fetch")

# 允许的信源类型（公开站点只收这三类）
ALLOWED_TYPES = {"official", "professional", "media"}


def strip_html(text: str) -> str:
    """去掉摘要里的 HTML 标签，只留纯文本。"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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


def fetch_one(source: dict, max_items: int, keep_days: int) -> list:
    """抓取单个信源，返回标准化条目列表。失败返回空列表并记日志。"""
    name = source.get("name", "未知来源")
    url = source.get("rss", "")
    stype = source.get("type", "")
    if stype not in ALLOWED_TYPES:
        log.warning("信源 [%s] 的 type=%r 不在允许范围内，已跳过", name, stype)
        return []
    try:
        # 先用 requests 抓（可控超时），再交给 feedparser 解析
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as e:  # noqa: BLE001 - 单个源失败只记日志
        log.warning("抓取信源 [%s] 失败：%s", name, e)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    items = []
    for entry in feed.entries[:max_items]:
        link = (entry.get("link") or "").strip()
        if not link:
            continue
        published = parse_time(entry)
        try:
            pub_dt = datetime.fromisoformat(published)
            if pub_dt < cutoff:
                continue  # 太旧的内容不要
        except Exception:
            pass
        items.append({
            "title": strip_html(entry.get("title", ""))[:200],
            "link": link,
            # 用链接的 md5 当稳定 id，用于去重
            "id": hashlib.md5(link.encode("utf-8")).hexdigest(),
            "summary_raw": strip_html(entry.get("summary", "") or entry.get("description", ""))[:500],
            "published": published,
            "source_name": name,
            "source_type": stype,
        })
    log.info("信源 [%s] 抓到 %d 条", name, len(items))
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
        if not src.get("rss"):
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
