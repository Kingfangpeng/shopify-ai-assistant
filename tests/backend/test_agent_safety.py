from app.services.ops_agent_service import _should_end


def test_replan_limit_does_not_end_without_report():
    state = {"response": "", "replan_count": 99}
    assert _should_end(state) == "execute"


def test_agent_tool_allowlist_excludes_ads():
    from app.tools import DEFAULT_LOCAL_AGENT_TOOLS
    names = {tool.name for tool in DEFAULT_LOCAL_AGENT_TOOLS}
    assert "get_orders_summary" in names
    assert not any("facebook" in name or "google" in name or "ads" in name for name in names)
