from app.pipeline.critic import build_critic_agent
from app.pipeline.digest_editor import build_editor_agent
from app.pipeline.judge import build_judge_agent
from app.pipeline.processing import build_processing_agent


def _temp(agent):
    cfg = agent.generate_content_config
    assert cfg is not None
    return cfg.temperature


def test_processing_agent_carries_temperature():
    assert _temp(build_processing_agent("gemini-flash-latest", temperature=0.0)) == 0.0


def test_critic_agent_carries_temperature():
    assert _temp(build_critic_agent("gemini-flash-latest", temperature=0.0)) == 0.0


def test_judge_agent_carries_temperature():
    assert _temp(build_judge_agent("gemini-flash-latest", temperature=0.0)) == 0.0


def test_editor_agent_carries_temperature():
    assert _temp(build_editor_agent("gemini-flash-latest", temperature=0.0)) == 0.0


def test_temperature_default_is_zero():
    # Factories default temperature to 0.0 when omitted.
    assert _temp(build_processing_agent("gemini-flash-latest")) == 0.0


def test_temperature_is_configurable():
    assert _temp(build_processing_agent("gemini-flash-latest", temperature=0.7)) == 0.7
