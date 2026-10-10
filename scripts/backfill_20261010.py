"""
一次性回填：给 data/processed.json 的历史条目补齐
1. disease_zh（关键词分类；已有明确值的不动）
2. 社交条目（controversial/unverified）的 author（从 x.com URL 提取）
3. 社交条目把正文里的"某 X 用户"还原成 @handle（仅当 handle 真实可得）
4. 社交条目空 timeline：从摘要里提取带日期的句子

用法：python scripts/backfill_20261010.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disease_classifier import classify_disease  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(BASE_DIR, "data", "processed.json")

HANDLE_RE = re.compile(r"x\.com/([^/]+)/status", re.I)
DATE_RE = re.compile(
    r"(\d{4}年\d{1,2}月(\d{1,2}[日号])?|\d{1,2}月\d{1,2}[日号]|\d{4}年代?|\d{4}年|"
    r"本月|上月|本月初|月末|近日|最近|目前|现在|当年|事发|当天|次日|随后)"
)
SENT_SPLIT = re.compile(r"[。；！？\n]")
BG_MARK = "【背景】"
SEC_MARK_RE = re.compile(r"^【[^】]{1,6}】")


def extract_author(url: str) -> str:
    m = HANDLE_RE.search(url or "")
    if not m:
        return ""
    h = m.group(1)
    if h.lower() in ("i", "home", "search", "explore"):
        return ""
    return h


def extract_timeline(summary: str, max_items: int = 6) -> list:
    text = summary or ""
    parts = text.split(BG_MARK)
    scope = parts[1] if len(parts) > 1 else text
    items, seen = [], set()
    for sent in SENT_SPLIT.split(scope):
        s = sent.strip()
        if len(s) < 8 or not DATE_RE.search(s):
            continue
        s = SEC_MARK_RE.sub("", s).strip()
        if s and s not in seen:
            seen.add(s)
            items.append(s[:150])
        if len(items) >= max_items:
            break
    return items


def main() -> None:
    with open(PROCESSED, encoding="utf-8") as f:
        processed = json.load(f)
    cache = processed.get("ai_cache", {})

    n_disease = n_author = n_unanon = n_tl = 0
    for url, rec in cache.items():
        if not isinstance(rec, dict):
            continue
        if not rec.get("disease_zh") or rec.get("disease_zh") == "未明确":
            d = classify_disease((rec.get("title_zh", "") or "") + " " + (rec.get("summary_zh", "") or ""))
            if d != "未明确":
                rec["disease_zh"] = d
                n_disease += 1
        if rec.get("source_type") in ("controversial", "unverified"):
            if not rec.get("author"):
                h = extract_author(url)
                if h:
                    rec["author"] = h
                    n_author += 1
            handle = rec.get("author", "")
            if handle:
                s = rec.get("summary_zh", "")
                new_s = s.replace("某 X 用户", "@" + handle).replace("发帖者", "@" + handle)
                if new_s != s:
                    rec["summary_zh"] = new_s
                    n_unanon += 1
            if not rec.get("timeline"):
                tl = extract_timeline(rec.get("summary_zh", ""))
                if tl:
                    rec["timeline"] = tl
                    n_tl += 1

    with open(PROCESSED, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)
    print("回填完成：disease_zh 新增 %d，author 新增 %d，去匿名化 %d，timeline 新增 %d"
          % (n_disease, n_author, n_unanon, n_tl))


if __name__ == "__main__":
    main()
