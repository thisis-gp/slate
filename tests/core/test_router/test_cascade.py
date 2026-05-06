from agentic_os.router.cascade import CascadeRouter, TierConfig

def test_cascade_router_selects_free_for_drafting():
    router = CascadeRouter(tiers={
        "free": TierConfig(provider="openrouter", model="qwen/qwen3-coder-480b:free"),
        "cheap": TierConfig(provider="openrouter", model="deepseek/deepseek-r1"),
        "premium": TierConfig(provider="anthropic", model="anthropic/claude-opus-4-7"),
    })
    tier = router.select_tier(task_type="drafting")
    assert tier == "free"

def test_cascade_router_selects_premium_for_review():
    router = CascadeRouter(tiers={
        "free": TierConfig(provider="openrouter", model="qwen/qwen3-coder-480b:free"),
        "cheap": TierConfig(provider="openrouter", model="deepseek/deepseek-r1"),
        "premium": TierConfig(provider="anthropic", model="anthropic/claude-opus-4-7"),
    })
    tier = router.select_tier(task_type="review")
    assert tier == "premium"

def test_cascade_router_selects_cheap_for_implementation():
    router = CascadeRouter(tiers={
        "free": TierConfig(provider="openrouter", model="qwen/qwen3-coder-480b:free"),
        "cheap": TierConfig(provider="openrouter", model="deepseek/deepseek-r1"),
        "premium": TierConfig(provider="anthropic", model="anthropic/claude-opus-4-7"),
    })
    tier = router.select_tier(task_type="implementation")
    assert tier == "cheap"
