"""疫情聚合站推送通知：检测重要新消息，推送到手机。

在 GitHub Actions 工作流中 run.py 之后运行。
环境变量（仓库 Secret，设哪个用哪个，可多选）：
  BARK_KEY            - Bark App 的设备 Key（iOS 推送）
  TELEGRAM_BOT_TOKEN  - Telegram 机器人 token（@BotFather 创建）
  TELEGRAM_CHAT_ID    - Telegram 接收者的 chat id
都不设时静默跳过，不影响主流程。

判定"重要"：官方来源（official）或标题/摘要含 severity 关键词。
每轮最多推送 3 条，避免打扰。
"""
import json
import logging
import os
import sys
import urllib.parse
import urllib.request

log = logging.getLogger("notify")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BARK_KEY = os.getenv("BARK_KEY", "").strip()
BARK_API = "https://api.day.app"
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# 严重程度关键词（标题或摘要命中即推送）
ALERT_KEYWORDS = [
    "确诊", "死亡", "爆发", "疫情", "紧急", "新增",
    "confirmed", "death", "deaths", "outbreak", "epidemic", "emergency",
    "вспышка", "подтвержден",  # 俄语：爆发、确诊
    "éclosion", "confirmé", "décès",  # 法语
    "brote", "confirmado", "muerte",  # 西语
]

# 突发疫情关键词（命中即最高优先级推送，标题加 🚨）
BREAKING_KEYWORDS = [
    "突发", "突现", "不明原因", "未知病原", "紧急警报", "卫生紧急",
    "breaking", "urgent", "alert", "mysterious", "unknown pathogen",
    "unknown pneumonia", "public health emergency", "pheic",
    "внезапная вспышка",  # 俄语：突发
    "urgence sanitaire",  # 法语：卫生紧急
    "emergencia sanitaria",  # 西语：卫生紧急
]

MAX_PUSH_PER_RUN = 3


def is_significant(rec: dict) -> bool:
    if rec.get("source_type") == "official":
        return True
    text = (rec.get("title_zh", "") + " " + rec.get("summary_zh", "")).lower()
    return any(kw.lower() in text for kw in ALERT_KEYWORDS)


def is_breaking(rec: dict) -> bool:
    """突发疫情：标题/摘要命中突发关键词。"""
    text = (rec.get("title_zh", "") + " " + rec.get("summary_zh", "")).lower()
    return any(kw.lower() in text for kw in BREAKING_KEYWORDS)


def send_bark(title: str, body: str, url: str) -> bool:
    if not BARK_KEY:
        return False
    try:
        path = "/{}/{}/{}".format(
            BARK_KEY,
            urllib.parse.quote(title[:60]),
            urllib.parse.quote(body[:200]),
        )
        if url:
            path += "?url=" + urllib.parse.quote(url)
        req = urllib.request.Request(
            BARK_API + path, headers={"User-Agent": "plague-aggregator/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("code") == 200
    except Exception as e:
        log.warning("Bark 推送失败：%s", e)
        return False


def send_telegram(title: str, body: str, url: str) -> bool:
    if not (TG_TOKEN and TG_CHAT_ID):
        return False
    try:
        text = "<b>{}</b>\n{}\n{}".format(
            _escape_html(title[:80]), _escape_html(body[:300]), _escape_html(url or "")
        )
        payload = json.dumps(
            {
                "chat_id": TG_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.telegram.org/bot{}/sendMessage".format(TG_TOKEN),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "plague-aggregator/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return bool(data.get("ok"))
    except Exception as e:
        log.warning("Telegram 推送失败：%s", e)
        return False


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def push(title: str, body: str, url: str) -> bool:
    """走已配置的通道推送，任一成功即算成功。"""
    ok = False
    if BARK_KEY:
        ok = send_bark(title, body, url) or ok
    if TG_TOKEN and TG_CHAT_ID:
        # Telegram 用纯文本标题（HTML 转义在 send_telegram 内处理）
        ok = send_telegram(title, body, url) or ok
    return ok


def main() -> None:
    if not (BARK_KEY or (TG_TOKEN and TG_CHAT_ID)):
        log.info("未设置推送密钥（BARK_KEY / TELEGRAM_BOT_TOKEN），跳过推送")
        return

    processed_path = os.path.join(BASE_DIR, "data", "processed.json")
    notified_path = os.path.join(BASE_DIR, "data", "notified.json")

    with open(processed_path, encoding="utf-8") as f:
        processed = json.load(f)

    notified = set()
    if os.path.exists(notified_path):
        try:
            with open(notified_path, encoding="utf-8") as f:
                notified = set(json.load(f).get("notified_ids", []))
        except Exception:
            pass

    cache = processed.get("ai_cache", {})
    candidates = []
    for link, rec in cache.items():
        cid = link  # 用 url 作为唯一 id
        if cid in notified:
            continue
        if is_significant(rec):
            candidates.append((rec.get("published", ""), cid, rec))

    # 突发优先：breaking 的排前面，再按时间倒序，取最新的 N 条
    candidates.sort(key=lambda x: (is_breaking(x[2]), x[0]), reverse=True)
    to_push = candidates[:MAX_PUSH_PER_RUN]

    sent = 0
    for _, cid, rec in to_push:
        prefix = "🚨【突发】" if is_breaking(rec) else "🦠 "
        title = prefix + (rec.get("title_zh") or "(无标题)")[:60]
        body = "{} | {}".format(
            rec.get("source_name", ""), (rec.get("summary_zh") or "")[:150]
        )
        if push(title, body, rec.get("url", "")):
            sent += 1
            log.info("已推送：%s", title[:40])
        notified.add(cid)

    # 落盘已推送 id（只保留最近 2000 个）
    with open(notified_path, "w", encoding="utf-8") as f:
        json.dump({"notified_ids": list(notified)[-2000:]}, f, ensure_ascii=False)

    log.info("本轮推送 %d 条", sent)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    main()
