import pytest
from app.tools.registry import registry


@pytest.mark.asyncio
async def test_tool_registry():
    tools = registry.list_tools()
    assert len(tools) >= 5
    tool_names = [t["name"] for t in tools]
    assert "web_research" in tool_names
    assert "document_generation" in tool_names
    assert "text_summarization" in tool_names
    assert "email_drafting" in tool_names
    assert "file_processing" in tool_names


@pytest.mark.asyncio
async def test_web_research_tool():
    tool = registry.get_tool("web_research")
    assert tool is not None
    result = await tool.run({"query": "AI Agent Frameworks", "num_results": 2})
    assert "findings" in result
    assert len(result["findings"]) == 2
    assert "summary" in result


@pytest.mark.asyncio
async def test_document_gen_tool():
    tool = registry.get_tool("document_generation")
    assert tool is not None
    result = await tool.run({
        "title": "Quarterly Plan",
        "format_type": "markdown",
        "sections": [{"heading": "Goals", "content": "Scale AI autonomy securely."}]
    })
    assert result["title"] == "Quarterly Plan"
    assert "content" in result
    assert result["word_count"] > 0


@pytest.mark.asyncio
async def test_email_drafting_tool_sensitivity():
    tool = registry.get_tool("email_drafting")
    assert tool is not None
    assert tool.is_sensitive is True
    assert tool.requires_approval is True

