"""
X 浏览采集注入：将从 X（推特）浏览搜集到的帖子注入为「争议说法」条目。

背景：sources.yaml 里的 X 信源（kind: x_search）需要付费的 X_BEARER_TOKEN，
本脚本走人工/浏览器浏览采集的替代路线，不依赖 X API。

用法：
    python scripts/x_browse_inject.py data/x_inbox.json

输入 JSON（数组，每条）：
    {"text": "帖子正文", "author": "用户名", "url": "https://x.com/.../status/...",
     "published": "ISO 时间字符串"}

处理：
- 用 data/processed.json 的 seen_ids 去重（已收录的不再加入）
- 用 fetch.is_relevant 做疫情相关性过滤
- 记录格式与 run.py 的 AI 关闭分支一致，source_type="controversial"，
  会显示在「争议说法」栏目并带醒目提示，不经过 AI 改写
- 成功后清空 inbox 文件，重新生成 docs/ 站点
"""

import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch import clean_title, is_relevant, strip_html  # noqa: E402
from generate import generate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("x_browse_inject")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_NAME = "X 推特 · plague 阴谋论（争议）"
SOURCE_TYPE = "controversial"


def _bigrams(text: str) -> set:
    t = re.sub(r"[\W_]+", "", text.lower())
    return {t[i:i + 2] for i in range(len(t) - 1)} or {t}


def _dedupe(records: list) -> list:
    """与 run.py 一致：标题二元组相似度 >= 0.6 视为同一事件，只保留最新一条。"""
    kept, kept_grams = [], []
    for rec in records:
        title = rec.get("title_zh") or ""
        title = re.sub(r"\s[-|–]\s[^-|–]{1,30}$", "", title)
        grams = _bigrams(title)
        if any(grams & g and len(grams & g) / len(grams | g) >= 0.6 for g in kept_grams):
            continue
        kept.append(rec)
        kept_grams.append(grams)
    return kept


def _norm_time(raw: str) -> str:
    if raw:
        s = str(raw).strip()
        # Grok / X 常见格式：8 Oct 2026, 08:20 GMT
        for fmt in ("%d %b %Y, %H:%M GMT", "%d %b %Y, %H:%M UTC"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def build_record(post: dict) -> dict | None:
    text = (post.get("text") or "").strip()
    link = (post.get("url") or "").strip()
    if not text or not link:
        return None
    # detail：人工撰写的详细中文解读（人物/说法/传播/背景），优先采用；
    # force：明确相关但未命中关键词过滤时跳过相关性检查
    detail = (post.get("detail") or "").strip()
    if not post.get("force") and not is_relevant(text, "") and not detail:
        log.info("丢弃无关内容：%s", text[:60])
        return None
    published = _norm_time(post.get("published"))
    summary = detail if detail else strip_html(text)
    return {
        "title_zh": (clean_title(text)[:200] or "(无标题)"),
        "summary_zh": summary[:1200] or "暂无摘要",
        "summary_en": "",
        "timeline": [],
        "treatment": "",
        "relevant": True,
        "url": link,
        "source_name": SOURCE_NAME,
        "published": published,
        "source_type": SOURCE_TYPE,
        "medical_advice": False,
        "ai_processed": False,
    }


def main(inbox_path: str) -> int:
    with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
        import yaml
        cfg = yaml.safe_load(f)
    site_cfg = cfg.get("site", {})

    processed_path = os.path.join(BASE_DIR, "data", "processed.json")
    try:
        with open(processed_path, encoding="utf-8") as f:
            processed = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        processed = {"seen_ids": [], "ai_cache": {}}
    seen = set(processed.get("seen_ids", []))
    ai_cache = processed.setdefault("ai_cache", {})

    with open(inbox_path, encoding="utf-8") as f:
        posts = json.load(f)
    if not isinstance(posts, list):
        log.error("inbox 文件格式错误，需要 JSON 数组")
        return 1

    added = 0
    for post in posts:
        rec = build_record(post if isinstance(post, dict) else {})
        if not rec:
            continue
        pid = hashlib.md5(rec["url"].encode("utf-8")).hexdigest()
        if pid in seen or rec["url"] in ai_cache:
            continue
        ai_cache[rec["url"]] = rec
        seen.add(pid)
        added += 1

    processed["seen_ids"] = list(seen)[-5000:]

    all_records = [r for r in ai_cache.values() if r.get("relevant") is not False]
    all_records.sort(key=lambda x: x.get("published", ""), reverse=True)
    all_records = _dedupe(all_records)
    all_records = all_records[: site_cfg.get("max_items_total", 300)]

    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    docs_dir = os.path.join(BASE_DIR, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    generate(all_records, cfg, docs_dir)

    # 成功后清空 inbox，避免重复处理
    with open(inbox_path, "w", encoding="utf-8") as f:
        json.dump([], f)

    log.info("注入完成：新增 %d 条，页面共 %d 条", added, len(all_records))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "data", "x_inbox.json")))
