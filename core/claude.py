from anthropic import AsyncAnthropic
from anthropic.types import Message
from mcp.shared.context import RequestContext
from mcp.types import CreateMessageRequestParams, CreateMessageResult, TextContent

class Claude:
    def __init__(self, model: str):
        self.client = AsyncAnthropic()
        self.model = model 

    
    
    async def sampling_callback(
        self,
        context: RequestContext,
        params: CreateMessageRequestParams,
    ) -> CreateMessageResult:
        """
        Called when the MCP server requests a message from the LLM.
        Converts MCP SamplingMessage format → OpenAI format → back to MCP.
        """
        messages = []
 
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

    
    
    def add_user_message(self, messages: list, message):
        user_message = {
            "role": "user",
            "content": message.content if isinstance(message, Message) else message,
        }
        messages.append(user_message)
    
    def add_assistant_message(self, messages: list, message):
        assistant_message = {
            "role": "assistant",
            "content": message.content if isinstance(message, Message) else message,
        }
        messages.append(assistant_message)
    
    def text_from_message(self, message: Message):
        return "\n".join([block.text for block in message.content if block.type == "text"])
    
    async def chat(
        self,
        messages,
        system=None,
        temperature=1.0,
        stop_sequences=[],
        tools=None,
        thinking=False,
        thinking_budget=1024,
    ) -> Message:
        params = {
            "model": self.model,
            "max_tokens": 8000,
            "messages": messages,
            "temperature": temperature,
            "stop_sequences": stop_sequences
        }

        if thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget
            }
        
        if tools:
            params["tools"] = tools 
        
        if system:
            params["system"] = system 

        message = await self.client.messages.create(**params)

        return message

    async def chat_stream(
        self,
        messages,
        system=None,
        temperature=1.0,
        stop_sequences=[],
        tools=None,
        thinking=False,
        thinking_budget=1024,
        on_event=None,
    ) -> Message:
        params = {
            "model": self.model,
            "max_tokens": 8000,
            "messages": messages,
            "temperature": temperature,
            "stop_sequences": stop_sequences,
        }

        if thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        if tools:
            params["tools"] = tools

        if system:
            params["system"] = system

        async with self.client.messages.stream(**params) as stream:
            if on_event:
                async for event in stream:
                    await on_event(event)
            else:
                async for event in stream:
                    pass 
            
            return await stream.get_final_message()


    
