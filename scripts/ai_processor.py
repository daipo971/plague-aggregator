"""
AI 处理模块：抓取新闻正文全文，生成专业级双语疫情简报。

输出结构（每条）：
- title_zh      中文标题
- summary_zh    完整中文摘要（250-350字）
- summary_en    English summary（150-200词）
- timeline      事件时间线（按时间先后，最多6条）
- treatment     治疗与防控措施（据报道整理）
- relevant      报道是否与疫情/鼠疫相关（AI 判断）
- medical_advice 是否涉及治疗/预防/就医建议

设计要点：
- API Key 只从环境变量 AI_API_KEY 读取，代码和配置里不出现明文密钥
- 先抓正文全文再做摘要，确保内容基于实际报道，不编造
- 单条失败只跳过该条并记日志，不中断整个任务
- 已处理过的链接走 ai_cache，不重复花钱调 AI
"""

import html
import json
import logging
import os
import re

import requests

log = logging.getLogger("ai")

# 专业版提示词：双语 + 时间线 + 治疗方法，严格基于报道原文
PROMPT_TEMPLATE = """你是一名资深疫情新闻编辑，擅长把外文疫情报道整理成专业的疫情简报。
请阅读下面的新闻（标题+正文），输出 JSON（只输出 JSON，不要其他文字）：

{{
  "title_zh": "中文标题（25字以内，准确、专业，点明事件核心）",
  "brief_zh": "一句话要点（40字以内，大白话，写清楚谁、在哪里、发生了什么，普通人一看就懂）",
  "summary_zh": "完整中文摘要（250-350字）：交代事件背景、发生地点、关键数据（病例数/死亡数/时间）、涉及机构、当前进展。只写报道中明确提到的内容，不要推测，不要编造数据。",
  "summary_en": "English summary (150-200 words): professional news-brief style. Cover what happened, where, key figures (cases/deaths/dates), parties involved, and current status. Based strictly on the reported facts, no speculation.",
  "timeline": ["时间线条目，按时间先后排列，最多6条。每条格式：日期（如报道明确）+ 事件；报道未明确日期的写'日期不详'+事件"],
  "treatment": "治疗与防控措施（200字以内）：整理报道中提到的治疗方法、药物、疫苗、隔离与防控措施；如报道未提及，写'报道未提及具体治疗方法'",
  "relevant": true/false（这篇报道是否与传染病/鼠疫疫情相关）,
  "medical_advice": true/false（内容是否涉及治疗、预防方法或就医建议）
}}

硬性要求：
1. 严格基于报道原文，不编造病例数、死亡数、日期等关键数据
2. 时间线按时间先后排序
3. 专业、客观的新闻语气，不渲染恐慌
4. timeline 为空数组是可以的，不要硬凑

新闻标题：{title}

新闻正文：
{text}
"""


def fetch_full_text(url: str, timeout: int = 15, max_chars: int = 4000) -> str:
    """
    抓取新闻正文全文：去掉脚本/导航/页眉页脚，提取 <p> 段落。
    失败返回空字符串（调用方降级用 RSS 摘要）。
    """
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; outbreak-aggregator/1.0)"},
        )
        resp.raise_for_status()
        raw = resp.text
        # 去掉脚本、样式、导航、页眉页脚等非正文区块
        cleaned_html = re.sub(
            r"(?is)<(script|style|nav|header|footer|aside|form|noscript)[^>]*>.*?</\1>",
            " ",
            raw,
        )
        # 取所有 <p> 段落，正文一般都在这里
        paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", cleaned_html)
        kept = []
        for p in paras:
            t = re.sub(r"<[^>]+>", " ", p)
            t = html.unescape(t)
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) >= 40:  # 过滤导航残留、版权行等过短文本
                kept.append(t)
        text = "\n".join(kept)
        if len(text) < 200:
            # <p> 太少（某些站点用 div 排版），兜底全文去标签
            t = re.sub(r"<[^>]+>", " ", raw)
            t = html.unescape(t)
            text = re.sub(r"\s+", " ", t).strip()
        return text[:max_chars]
    except Exception as e:  # noqa: BLE001 - 抓正文失败只记日志
        log.warning("正文抓取失败 %s：%s", url, e)
        return ""


class AIProvider:
    """AI 接口基类：子类实现 summarize() 即可接入新模型。"""

    def summarize(self, title: str, text: str) -> dict | None:
        raise NotImplementedError


def _parse_result(content: str) -> dict | None:
    """解析 AI 返回的 JSON，字段做长度保护。失败返回 None。"""
    try:
        data = json.loads(content)
    except Exception:
        # 兼容模型在 JSON 前后加了说明文字的情况
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            data = json.loads(content[start:end])
        except Exception:
            return None
    timeline = data.get("timeline") or []
    if not isinstance(timeline, list):
        timeline = []
    timeline = [str(t)[:150] for t in timeline[:6]]
    return {
        "title_zh": str(data.get("title_zh", ""))[:80],
        "brief_zh": str(data.get("brief_zh", ""))[:80],
        "summary_zh": str(data.get("summary_zh", ""))[:600],
        "summary_en": str(data.get("summary_en", ""))[:900],
        "timeline": timeline,
        "treatment": str(data.get("treatment", ""))[:400],
        "relevant": bool(data.get("relevant", True)),
        "medical_advice": bool(data.get("medical_advice", False)),
    }


class OpenAICompatibleProvider(AIProvider):
    """OpenAI 兼容接口：OpenAI / DeepSeek / 智谱 / 通义千问等都走这里。"""

    def __init__(self, base_url: str, model: str, api_key: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def summarize(self, title: str, text: str) -> dict | None:
        prompt = PROMPT_TEMPLATE.format(title=title[:300], text=text[:3500])
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    # 尽量让模型直接返回 JSON（不支持的接口会忽略该参数）
                    "response_format": {"type": "json_object"},
                    "max_tokens": 2000,
                    "temperature": 0.3,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _parse_result(content)
        except Exception as e:  # noqa: BLE001 - 单条失败只记日志
            log.warning("AI 调用失败（openai_compatible）：%s", e)
            return None


class AnthropicProvider(AIProvider):
    """Anthropic 官方接口。"""

    def __init__(self, model: str, api_key: str, timeout: int):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def summarize(self, title: str, text: str) -> dict | None:
        prompt = PROMPT_TEMPLATE.format(title=title[:300], text=text[:3500])
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]
            return _parse_result(content)
        except Exception as e:  # noqa: BLE001 - 单条失败只记日志
            log.warning("AI 调用失败（anthropic）：%s", e)
            return None


def get_provider(ai_cfg: dict) -> AIProvider | None:
    """根据配置创建对应的 AI provider。拿不到 Key 返回 None。"""
    api_key = os.environ.get("AI_API_KEY", "").strip()
    if not api_key:
        log.warning("未检测到环境变量 AI_API_KEY，AI 处理将跳过")
        return None
    name = ai_cfg.get("provider", "openai_compatible")
    timeout = ai_cfg.get("timeout", 60)
    if name == "anthropic":
        model = ai_cfg.get("anthropic", {}).get("model", "")
        if not model:
            log.warning("anthropic 的 model 未配置，已跳过 AI 处理")
            return None
        return AnthropicProvider(model, api_key, timeout)
    # 默认走 OpenAI 兼容接口
    oc = ai_cfg.get("openai_compatible", {})
    return OpenAICompatibleProvider(
        oc.get("base_url", ""), oc.get("model", ""), api_key, timeout
    )


def _empty_record(item: dict, url: str) -> dict:
    """降级记录：新字段给空值，保证页面渲染不报错。"""
    return {
        "title_zh": item["title"] or "(无标题)",
        "brief_zh": "",
        "retries": 0,
        "summary_zh": (item.get("summary_raw") or "暂无摘要")[:200],
        "summary_en": "",
        "timeline": [],
        "treatment": "",
        "relevant": True,
        "url": url,
        "source_name": item["source_name"],
        "published": item["published"],
        "source_type": item["source_type"],
        "medical_advice": False,
        "ai_processed": False,
    }


def _is_legacy(rec: dict) -> bool:
    """老格式缓存（缺 timeline 字段）需要升级成专业版。"""
    return "timeline" not in rec


def _legacy_to_item(rec: dict, url: str) -> dict:
    """把老缓存记录拼成可处理的条目（标题用中文标题，正文重新抓取）。"""
    return {
        "title": rec.get("title_zh", ""),
        "link": url,
        "summary_raw": rec.get("summary_zh", ""),
        "source_name": rec.get("source_name", ""),
        "published": rec.get("published", ""),
        "source_type": rec.get("source_type", ""),
    }


def _make_record(item: dict, url: str, ai_out: dict) -> dict:
    """由 AI 输出组装标准记录。"""
    return {
        "title_zh": ai_out["title_zh"] or item["title"],
        "brief_zh": ai_out.get("brief_zh", ""),
        "summary_zh": ai_out["summary_zh"],
        "summary_en": ai_out["summary_en"],
        "timeline": ai_out["timeline"],
        "treatment": ai_out["treatment"],
        "relevant": ai_out["relevant"],
        "url": url,
        "source_name": item["source_name"],
        "published": item["published"],
        "source_type": item["source_type"],
        "medical_advice": ai_out["medical_advice"],
        "ai_processed": True,
    }


def _upgrade_one(item: dict, provider: AIProvider, ai_cache: dict) -> dict:
    """
    升级单条老记录：成功则替换为专业版；失败则保留原摘要，
    并标记 timeline=[] 避免每轮重复浪费预算。
    """
    url = item["link"]
    rec = ai_cache[url]
    full_text = fetch_full_text(url) or item.get("summary_raw", "")
    ai_out = provider.summarize(item["title"], full_text)
    if ai_out is None:
        log.warning("老记录升级失败，保留原摘要：%s", url)
        rec["timeline"] = []
        return rec
    new_rec = _make_record(item, url, ai_out)
    ai_cache[url] = new_rec
    return new_rec


def _needs_retry(rec: dict) -> bool:
    """未成功 AI 处理（原文直出）且重试次数未超限的记录，下次运行继续补跑。"""
    return rec.get("ai_processed") is False and not _is_legacy(rec) and rec.get("retries", 0) < MAX_RETRIES


MAX_RETRIES = 3


def process_items(items: list, processed: dict, ai_cfg: dict) -> list:
    """
    对新条目逐条处理：抓正文全文 -> 调 AI 生成中文简报。
    - 之前因预算用完或失败而未翻译的记录，优先补跑（最新的优先）
    - 已在 ai_cache 且为新格式的直接复用，不花钱
    - 单条 AI 失败：记为原文直出并计入重试次数，之后仍会补跑，最多 MAX_RETRIES 次
    - 每轮最多 max_per_run 次 AI 调用，剩下的下次运行继续
    """
    provider = get_provider(ai_cfg)
    ai_cache = processed.setdefault("ai_cache", {})
    max_per_run = ai_cfg.get("max_per_run", 30)
    ai_calls = 0

    def translate(item: dict, url: str):
        """调用 AI；成功返回记录，失败返回 None。"""
        nonlocal ai_calls
        ai_calls += 1
        full_text = fetch_full_text(url) or item.get("summary_raw", "")
        ai_out = provider.summarize(item["title"], full_text)
        if ai_out is None:
            log.warning("条目 AI 处理失败：%s", url)
            return None
        return _make_record(item, url, ai_out)

    # 1) 补跑之前未翻译的记录（最新的优先）
    if provider is not None:
        pending = [(u, r) for u, r in ai_cache.items() if _needs_retry(r)]
        pending.sort(key=lambda x: x[1].get("published", ""), reverse=True)
        for url, rec in pending:
            if ai_calls >= max_per_run:
                break
            new_rec = translate(_legacy_to_item(rec, url), url)
            if new_rec is not None:
                ai_cache[url] = new_rec
            else:
                rec["retries"] = rec.get("retries", 0) + 1

    # 2) 处理本轮新条目
    results = []
    for item in items:
        url = item["link"]
        if url in ai_cache:
            rec = ai_cache[url]
            if _is_legacy(rec) and provider is not None and ai_calls < max_per_run:
                results.append(_upgrade_one(item, provider, ai_cache))
                ai_calls += 1
            else:
                results.append(rec)
            continue
        if provider is None or ai_calls >= max_per_run:
            rec = _empty_record(item, url)  # 预算用完：原文直出，下次补跑
            ai_cache[url] = rec
            results.append(rec)
            continue
        new_rec = translate(item, url)
        if new_rec is None:
            rec = _empty_record(item, url)
            rec["retries"] = 1
            ai_cache[url] = rec
            results.append(rec)
        else:
            ai_cache[url] = new_rec
            results.append(new_rec)

    log.info("AI 处理完成：本轮调用 %d 次，本轮新条目 %d 条", ai_calls, len(results))
    return results
