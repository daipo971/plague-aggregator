"""
AI 处理模块：对抓取到的条目生成中文标题、一句话中文摘要，
并判断是否涉及治疗/预防/就医建议。

设计要点：
- 统一接口：AIProvider.summarize()，通过 config.yaml 的 ai.provider 切换模型
- API Key 只从环境变量 AI_API_KEY 读取，代码和配置里不出现明文密钥
- 单条失败只跳过该条并记日志，不中断整个任务
- 已处理过的链接走 ai_cache，不重复花钱调 AI
"""

import json
import logging
import os

import requests

log = logging.getLogger("ai")

# 要求 AI 输出的 JSON 字段说明（code 里再补上链接等字段）
PROMPT_TEMPLATE = """你是一名疫情信息编辑。请阅读下面的新闻条目，输出 JSON（只输出 JSON，不要其他文字）：

{{
  "title_zh": "中文标题（20字以内，准确简洁）",
  "summary_zh": "一句话中文摘要（60字以内，说清发生了什么）",
  "medical_advice": true/false（内容是否涉及治疗、预防方法或就医建议）
}}

条目原文标题：{title}
条目原文摘要：{text}
"""


class AIProvider:
    """AI 接口基类：子类实现 summarize() 即可接入新模型。"""

    def summarize(self, title: str, text: str) -> dict | None:
        raise NotImplementedError


class OpenAICompatibleProvider(AIProvider):
    """OpenAI 兼容接口：OpenAI / DeepSeek / 通义千问等都走这里。"""

    def __init__(self, base_url: str, model: str, api_key: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def summarize(self, title: str, text: str) -> dict | None:
        prompt = PROMPT_TEMPLATE.format(title=title[:300], text=text[:800])
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    # 尽量让模型直接返回 JSON（不支持的接口会忽略该参数）
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            return {
                "title_zh": str(data.get("title_zh", ""))[:60],
                "summary_zh": str(data.get("summary_zh", ""))[:200],
                "medical_advice": bool(data.get("medical_advice", False)),
            }
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
        prompt = PROMPT_TEMPLATE.format(title=title[:300], text=text[:800])
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
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            # 取出返回文本里的 JSON 部分
            content = resp.json()["content"][0]["text"]
            start = content.find("{")
            end = content.rfind("}") + 1
            data = json.loads(content[start:end])
            return {
                "title_zh": str(data.get("title_zh", ""))[:60],
                "summary_zh": str(data.get("summary_zh", ""))[:200],
                "medical_advice": bool(data.get("medical_advice", False)),
            }
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


def process_items(items: list, processed: dict, ai_cfg: dict) -> list:
    """
    对新条目逐条调 AI。返回处理好的条目列表（固定 JSON 结构）。
    - 已在 ai_cache 里的直接复用，不花钱
    - 单条 AI 失败则跳过该条，只记日志
    - 超过 max_per_run 条的，剩下的本次跳过（下次跑再处理）
    """
    provider = get_provider(ai_cfg)
    ai_cache = processed.setdefault("ai_cache", {})
    max_per_run = ai_cfg.get("max_per_run", 30)

    results = []
    ai_calls = 0
    for item in items:
        url = item["link"]
        if url in ai_cache:
            results.append(ai_cache[url])  # 命中缓存，不调 AI
            continue
        if provider is None or ai_calls >= max_per_run:
            # 没有 AI（或达到本轮上限）：降级为原文直出，保证页面不空
            fallback = {
                "title_zh": item["title"] or "(无标题)",
                "summary_zh": (item["summary_raw"] or "暂无摘要")[:200],
                "url": url,
                "source_name": item["source_name"],
                "published": item["published"],
                "source_type": item["source_type"],
                "medical_advice": False,
                "ai_processed": False,
            }
            ai_cache[url] = fallback
            results.append(fallback)
            continue
        ai_calls += 1
        ai_out = provider.summarize(item["title"], item["summary_raw"])
        if ai_out is None:
            log.warning("条目 AI 处理失败，已跳过：%s", url)
            continue  # 按需求：跳过该条，不中断任务
        record = {
            "title_zh": ai_out["title_zh"] or item["title"],
            "summary_zh": ai_out["summary_zh"],
            "url": url,
            "source_name": item["source_name"],
            "published": item["published"],
            "source_type": item["source_type"],
            "medical_advice": ai_out["medical_advice"],
            "ai_processed": True,
        }
        ai_cache[url] = record
        results.append(record)

    log.info("AI 处理完成：新调用 %d 次，共产出 %d 条", ai_calls, len(results))
    return results
