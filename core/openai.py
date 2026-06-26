from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from openai import AsyncOpenAI
from mcp.shared.context import RequestContext
from mcp.types import CreateMessageRequestParams, CreateMessageResult, TextContent


@dataclass
class TextBlock:
    type: str
    text: str


@dataclass
class ToolUseBlock:
    type: str
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str
    parsed_arguments: dict[str, Any]


@dataclass
class OpenAIMessage:
    content: list[Any]
    stop_reason: str
    model: str
    tool_calls: list[ToolCall]
    text: str


class OpenAIService:
    supports_stream = False

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: Optional[str] = None,
        tool_mode: str = "auto",
    ):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.tool_mode = tool_mode.lower()

    async def sampling_callback(
        self,
        context: RequestContext,
        params: CreateMessageRequestParams,
    ) -> CreateMessageResult:
        messages: list[dict[str, Any]] = []

        if params.systemPrompt:
            messages.append({"role": "system", "content": params.systemPrompt})

        for msg in params.messages:
            if msg.content.type == "text":
                messages.append({"role": msg.role, "content": msg.content.text})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=params.maxTokens or 1000,
        )

        text = response.choices[0].message.content or ""

        return CreateMessageResult(
            role="assistant",
            model=self.model,
            content=TextContent(type="text", text=text),
        )

    def _convert_tools(self, tools: Optional[list[dict[str, Any]]]) -> Optional[list[dict[str, Any]]]:
        if not tools:
            return None

        converted: list[dict[str, Any]] = []
        for tool in tools:
            params = tool.get("input_schema") or {"type": "object", "properties": {}}
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description") or "",
                        "parameters": params,
                    },
                }
            )

        return converted

    def _tool_payload(
        self,
        tools: Optional[list[dict[str, Any]]],
    ) -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
        if self.tool_mode == "none":
            return None, None

        converted = self._convert_tools(tools)
        if converted:
            return converted, "auto"

        return None, None

    def _is_tool_validation_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return any(
            token in message
            for token in (
                "tool call validation failed",
                "failed to call a function",
                "tool_use_failed",
                "invalid_request_error",
            )
        )

    def _build_message(self, response) -> OpenAIMessage:
        choice = response.choices[0]
        message = choice.message

        text = message.content or ""
        content_blocks: list[Any] = []
        if text:
            content_blocks.append(TextBlock(type="text", text=text))

        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for call in message.tool_calls:
                arguments_str = call.function.arguments or "{}"
                try:
                    parsed = json.loads(arguments_str) if arguments_str else {}
                except json.JSONDecodeError:
                    parsed = {}

                tool_calls.append(
                    ToolCall(
                        id=call.id,
                        name=call.function.name,
                        arguments=arguments_str,
                        parsed_arguments=parsed,
                    )
                )

                content_blocks.append(
                    ToolUseBlock(
                        type="tool_use",
                        id=call.id,
                        name=call.function.name,
                        input=parsed,
                    )
                )

        stop_reason = "tool_use" if tool_calls else "end_turn"

        return OpenAIMessage(
            content=content_blocks,
            stop_reason=stop_reason,
            model=self.model,
            tool_calls=tool_calls,
            text=text,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        system: Optional[str] = None,
        temperature: float = 1.0,
        stop_sequences: Optional[list[str]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> OpenAIMessage:
        payload_messages = list(messages)
        if system:
            payload_messages.insert(0, {"role": "system", "content": system})

        tools_payload, tool_choice = self._tool_payload(tools)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=payload_messages,
                temperature=temperature,
                stop=stop_sequences or None,
                tools=tools_payload,
                tool_choice=tool_choice,
            )
        except Exception as e:
            if tool_choice and self._is_tool_validation_error(e):
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=payload_messages,
                    temperature=temperature,
                    stop=stop_sequences or None,
                )
                message = self._build_message(response)
                note = (
                    "Tool calling was disabled because the model returned an "
                    "unsupported tool name. Switch to a tool-capable model or "
                    "set OPENAI_TOOL_MODE=none."
                )
                message.text = f"{note}\n\n{message.text}" if message.text else note
                message.content = [TextBlock(type="text", text=message.text)]
                message.tool_calls = []
                message.stop_reason = "end_turn"
                return message
            raise

        return self._build_message(response)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: Optional[str] = None,
        temperature: float = 1.0,
        stop_sequences: Optional[list[str]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        on_event=None,
    ) -> OpenAIMessage:
        return await self.chat(
            messages=messages,
            system=system,
            temperature=temperature,
            stop_sequences=stop_sequences,
            tools=tools,
        )

    def add_user_message(self, messages: list[dict[str, Any]], message: Any) -> None:
        if isinstance(message, list) and message and isinstance(message[0], dict):
            if all(item.get("type") == "tool_result" for item in message):
                for item in message:
                    content = item.get("content", "")
                    if not isinstance(content, str):
                        content = json.dumps(content)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": content,
                        }
                    )
                return

        user_message = {"role": "user", "content": message}
        messages.append(user_message)

    def add_assistant_message(self, messages: list[dict[str, Any]], message: OpenAIMessage) -> None:
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": message.text,
        }

        if message.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in message.tool_calls
            ]

        messages.append(assistant_message)

    def text_from_message(self, message: OpenAIMessage) -> str:
        return message.text
