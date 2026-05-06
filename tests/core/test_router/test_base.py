from agentic_os.router.base import Message, LLMResponse, ModelTier

def test_message_construction():
    msg = Message(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"

def test_llm_response_has_cost():
    resp = LLMResponse(
        content="response text",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cost_usd=0.001,
        model="test/model",
    )
    assert resp.cost_usd == 0.001
    assert resp.total_tokens == 150

def test_model_tier_values():
    assert ModelTier.FREE == "free"
    assert ModelTier.CHEAP == "cheap"
    assert ModelTier.PREMIUM == "premium"
