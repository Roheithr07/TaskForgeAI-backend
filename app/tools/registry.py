import asyncio
import time
from typing import Dict, List, Optional, Any
from app.tools.base import BaseTool
from app.tools.web_research import WebResearchTool
from app.tools.document_gen import DocumentGenerationTool
from app.tools.text_summarize import TextSummarizationTool
from app.tools.email_draft import EmailDraftingTool
from app.tools.email_send import EmailSendingTool
from app.tools.file_process import FileProcessingTool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        tools = [
            WebResearchTool(),
            DocumentGenerationTool(),
            TextSummarizationTool(),
            EmailDraftingTool(),
            EmailSendingTool(),
            FileProcessingTool()
        ]
        for t in tools:
            self._tools[t.name] = t

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.get_info() for tool in self._tools.values()]

    def is_sensitive(self, tool_name: str) -> bool:
        tool = self.get_tool(tool_name)
        return tool.is_sensitive if tool else False

    async def execute_tool(self, name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a registered tool with input validation, timeout enforcement,
        timing metrics, and telemetry audit logging.
        """
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' is not registered in central tool registry.")

        start_time = time.time()
        try:
            # Validate input schema first
            validated_input = tool.input_model(**input_data)
            
            # Execute with tool-configured timeout
            output = await asyncio.wait_for(
                tool.run(validated_input.model_dump()),
                timeout=tool.timeout_seconds
            )
            duration_ms = (time.time() - start_time) * 1000
            tool.record_execution(success=True, duration_ms=duration_ms)
            return output
        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            err_msg = f"Tool '{name}' timed out after {tool.timeout_seconds}s."
            tool.record_execution(success=False, duration_ms=duration_ms, error=err_msg)
            raise TimeoutError(err_msg)
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            err_msg = str(e)
            tool.record_execution(success=False, duration_ms=duration_ms, error=err_msg)
            raise e


registry = ToolRegistry()
