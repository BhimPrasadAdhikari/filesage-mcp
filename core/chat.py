"""
Base agentic loop - LLM <-> tool_use.

Drives the conversation forward:
    1. Sends messages + available tools to the LLM
    2. If the LLM responds with tool_use, executes them via ToolManager
    3. Appends results and loops until the LLM gives a final text response

"""
import json
import os

from core.tool_manager import ToolManager
from mcp_client import MCPClient


class Chat:

    def __init__(self, llm_service, clients: dict[str, MCPClient]):
        self.llm_service = llm_service
        self.clients = clients
        self.messages: list[dict] = []
        self.max_history_chars = self._int_env("MAX_HISTORY_CHARS", 12000)
        self.max_history_messages = self._int_env("MAX_HISTORY_MESSAGES", 40)

    @property
    def supports_stream(self) -> bool:
        return bool(getattr(self.llm_service, "supports_stream", True))

    def _int_env(self, name: str, default: int) -> int:
        value = os.getenv(name)
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def reset(self) -> None:
        self.messages = []

    def _message_len(self, message: dict) -> int:
        content = message.get("content", "")
        if isinstance(content, str):
            return len(content)
        return len(json.dumps(content))

    def _truncate_history(self) -> None:
        if self.max_history_messages > 0 and len(self.messages) > self.max_history_messages:
            self.messages = self.messages[-self.max_history_messages :]

        if self.max_history_chars <= 0:
            return

        total = sum(self._message_len(msg) for msg in self.messages)
        if total <= self.max_history_chars:
            return

        trimmed: list[dict] = []
        running = 0
        for msg in reversed(self.messages):
            msg_len = self._message_len(msg)
            if trimmed and running + msg_len > self.max_history_chars:
                break
            trimmed.append(msg)
            running += msg_len

        self.messages = list(reversed(trimmed))

    async def _process_query(self, query: str) -> None:
        self.messages.append({"role": "user", "content": query})

    async def run(
        self,
        query: str,
        stream: bool = False,
        on_event=None,
    ) -> str:
        final_response = ""
        await self._process_query(query)
        self._truncate_history()

        while True:
            use_stream = bool(stream and on_event and self.supports_stream)
            if use_stream:
                response = await self.llm_service.chat_stream(
                    messages=self.messages,
                    tools=await ToolManager.get_all_tools(self.clients),
                    on_event=on_event,
                )
            else:
                response = await self.llm_service.chat(
                    messages=self.messages,
                    tools=await ToolManager.get_all_tools(self.clients),
                )

            self.llm_service.add_assistant_message(self.messages, response)
            self._truncate_history()

            if response.stop_reason == "tool_use":
                if not use_stream:
                    print(self.llm_service.text_from_message(response))

                tool_results = await ToolManager.execute_tool_requests(
                    self.clients, response
                )
                self.llm_service.add_user_message(self.messages, tool_results)
                self._truncate_history()
            else:
                final_response = self.llm_service.text_from_message(response)
                break

        return final_response