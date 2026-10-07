"""
总入口：抓取 -> AI 处理 -> 合并历史 -> 生成页面。
GitHub Actions 每 30 分钟运行一次这个文件。
"""

import json
import logging
import os
import sys

import yaml

# 让 run.py 无论从哪运行都能 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_processor import process_items  # noqa: E402
from fetch import fetch_all  # noqa: E402
from generate import generate  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("run")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    # 1. 读配置
    with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    site_cfg = cfg.get("site", {})
    processed_path = os.path.join(BASE_DIR, "data", "processed.json")
    docs_dir = os.path.join(BASE_DIR, "docs")
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)

    # 2. 抓取新内容
    new_items, processed = fetch_all(
        os.path.join(BASE_DIR, "sources.yaml"), processed_path, cfg
    )

    # 3. AI 处理（失败自动跳过/降级，不会中断）
    ai_cfg = cfg.get("ai", {})
    if ai_cfg.get("enabled", True):
        fresh = process_items(new_items, processed, ai_cfg)
    else:
        log.info("AI 已关闭（ai.enabled=false），使用原文直出模式")
        fresh = []
        ai_cache = processed.setdefault("ai_cache", {})
        for item in new_items:
            rec = {
                "title_zh": item["title"] or "(无标题)",
                "summary_zh": (item["summary_raw"] or "暂无摘要")[:200],
                "summary_en": "",
                "timeline": [],
                "treatment": "",
                "relevant": True,
                "url": item["link"],
                "source_name": item["source_name"],
                "published": item["published"],
                "source_type": item["source_type"],
                "medical_advice": False,
                "ai_processed": False,
            }
            ai_cache[item["link"]] = rec
            fresh.append(rec)

    # 4. 合并历史记录：新条目 + 缓存里的旧条目，按时间倒序截断
    seen_ids = set(processed.get("seen_ids", []))
    for item in new_items:
        seen_ids.add(item["id"])
    processed["seen_ids"] = list(seen_ids)[-5000:]  # 去重表只留最近 5000 个

    all_records = list(processed.get("ai_cache", {}).values())
    all_records.sort(key=lambda x: x.get("published", ""), reverse=True)
    all_records = all_records[: site_cfg.get("max_items_total", 300)]

    # 5. 落盘 + 生成页面
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)
    generate(all_records, cfg, docs_dir)
    log.info("本轮完成：新增 %d 条，页面共 %d 条", len(fresh), len(all_records))


if __name__ == "__main__":
    main()
