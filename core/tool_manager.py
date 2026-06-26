"""
Bridge the MCP tool layer and the LLM client.

This is not the server code, this all happens on the MCP client side.

What does this file do:
1. Collect tool definitions from all connected MCP clients.
2. Route tool_use blocks from the LLM response to the correct MCP client.
3. Return formatted tool_result blocks back into the conversation.
"""

import json
import os
from typing import Optional 

from anthropic.types import Message, ToolResultBlockParam
from mcp.types import CallToolResult, TextContent 

from mcp_client import MCPClient

class ToolManager:

    @classmethod
    async def get_all_tools(cls, clients: dict[str, MCPClient]) -> list[dict]:
        tools = []
        for client in clients.values():
            tool_models = await client.list_tools()
            tools += [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.inputSchema,
                }

                for t in tool_models
            ]
        
        return tools 
    
    @classmethod
    async def _find_client_for_tool(
        cls,
        clients: list[MCPClient],
        tool_name: str,
    ) -> Optional[MCPClient]:
        """Find the first connected client that exposes the requested tool."""
        for client in clients:
            tools = await client.list_tools()
            if any(t.name == tool_name for t in tools):
                return client 
        return None 
    
    @classmethod
    def _build_result(cls, tool_use_id: str, content: str, is_error: bool) -> ToolResultBlockParam:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": is_error,
        }
    
    @classmethod
    async def execute_tool_requests(
        cls,
        clients: dict[str, MCPClient],
        message: Message,
    ) -> list[ToolResultBlockParam]:
        """Execute all tool_use blocks in the LLM response message."""

        max_result_chars = cls._int_env("MAX_TOOL_RESULT_CHARS", 8000)
        results: list[ToolResultBlockParam] = []
        tool_blocks = [b for b in message.content if b.type == "tool_use"]
        for block in tool_blocks:
            tool_use_id = block.id
            tool_name = block.name
            tool_input = block.input

            client = await cls._find_client_for_tool(list(clients.values()), tool_name)

            if not client:
                results.append(
                    cls._build_result(
                        tool_use_id,
                        f"tool '{tool_name}' not found on any connected client.",
                        True,
                    )
                )
                continue

            try:
                output: CallToolResult | None = await client.call_tool(
                    tool_name, tool_input
                )

                if output:
                    text_items = [
                        item.text
                        for item in output.content
                        if isinstance(item, TextContent)
                    ]

                    content = json.dumps(text_items)
                    is_error = bool(output.isError)
                else:
                    content = "[]"
                    is_error = False
            except Exception as e:
                content = json.dumps({"error": str(e)})
                is_error = True

            if max_result_chars > 0 and len(content) > max_result_chars:
                content = (
                    content[: max_result_chars - 15]
                    + "...[truncated]"
                )

            results.append(cls._build_result(tool_use_id, content, is_error))

        return results

    @staticmethod
    def _int_env(name: str, default: int) -> int:
        value = os.getenv(name)
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default
        

            
