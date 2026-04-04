from src.narrativeos.providers import AnthropicProvider, LocalRuleBasedProvider, OpenAIProvider


def test_provider_abstractions_exist():
    assert LocalRuleBasedProvider().generate_json(system_prompt="a", user_prompt="b") == {"candidate_events": []}
    assert hasattr(OpenAIProvider, "generate_json")
    assert hasattr(AnthropicProvider, "generate_json")
