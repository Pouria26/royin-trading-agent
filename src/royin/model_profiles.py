"""Explicit model/origin bindings verified against provider catalogs on 2026-10-23."""

PROVIDER_ORIGINS = {
    "boxapi": "https://ai.boxapi.ir/ai/v1",
    "devora": "https://api.devora.my.id/v1",
    "dahl": "https://inference.dahl.global/v1",
    "river": "https://api.river.ai/v1",
    "apmix": "https://api.apmix.ai/v1",
    "codecraft": "https://codecraftapi.com/v1",
}
PROVIDER_MODELS = {
    "boxapi": ("gpt-6-luna", "gpt-5.6-luna", "gpt-5.4-mini"),
    "devora": (
        "devora-01/deepseek/deepseek-v4.1-flash", "devora-01/deepseek/deepseek-v4-pro",
        "devora-01/stealth/dvr-v0.1-fp8", "devora-01/zai/glm-5.2", "devora-01/zai/glm-5.3-flash",
    ),
    "dahl": ("MiniMaxAI/MiniMax-M2.7", "zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4-Flash-0731"),
    "river": ("deepseek-ai/DeepSeek-V4.1-Flash", "deepseek-ai/DeepSeek-V4.1-Flash-1017", "zai-org/GLM-5.3-Flash"),
    "apmix": ("claude-sonnet-4-6-free",),
    "codecraft": ("claude-opus-5.5", "claude-sonnet-5", "gpt-5.6-sol", "gemini-3.7-flash",
                  "glm-5.3", "deepseek-v4-pro-max"),
}


def model_settings(provider, model, *, role):
    if provider == "boxapi":
        return {"max_tokens":1024 if role else 512,"openai_reasoning_effort":"none"}
    settings = {"max_tokens":8192,"parallel_tool_calls":False}
    if provider == "river":
        settings["openai_reasoning_effort"] = "low" if "glm" in model.lower() else "none"
        return settings
    if provider == "codecraft":
        return settings
    if "glm-5.3" in model.lower():
        settings.update(openai_reasoning_effort="low",extra_body={"thinking":{"type":"enabled"}})
    elif "deepseek" in model.lower():
        settings["extra_body"] = {"thinking":{"type":"disabled"}}
    return settings


def reasoning_label(provider, model):
    if provider == "codecraft":
        return "provider_default"
    if provider == "boxapi" or "deepseek" in model.lower():
        return "none"
    return "low" if "glm-5.3" in model.lower() else "provider_default"


def matches_provider_model(provider, model):
    """An approved provider label cannot claim another catalog's model identity."""
    return isinstance(provider,str) and model in PROVIDER_MODELS.get(provider,())
