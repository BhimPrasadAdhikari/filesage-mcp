# Part 3: Deploying and Debugging MCP in the Real World

If Part 1 was theory and Part 2 was architecture, Part 3 is about reality. Code never survives contact with the real world unscathed. When you deploy an MCP server—especially one interacting with dozens of free, API-compatible endpoints—things break. 

In this post, we’ll walk through the hard engineering lessons we learned when deploying FileSage MCP. We stripped Claude dependency, introduced agnostic LLM support (like Groq), debugged inspector failures over HTTP/SSE, handled token limits, and stabilized tool-calling against hallucinating models. 

This is the definitive guide on making MCP servers bulletproof.

---

## 1. Agnosing the LLM Provider

Our first goal was breaking the hard dependency on Anthropic's Claude. We wanted FileSage to run on free, fast, OpenAI-compatible APIs (like Groq) without ripping out the MCP agentic loop.

We achieved this by abstracting the LLM into a generic service interface and moving provider logic out of the core pipeline.

### The OpenAI Service Adapter

We created `OpenAIService` to act as an adapter between the Anthropic-style MCP message format and standard OpenAI chat completions.

```python
# core/openai.py
class OpenAIService:
    def __init__(self, model: str, api_key: str, base_url: str = None, tool_mode: str = "auto"):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.tool_mode = tool_mode.lower()
        
    async def chat(self, messages, system=None, temperature=1.0, stop_sequences=None, tools=None):
        payload_messages = list(messages)
        if system:
            payload_messages.insert(0, {"role": "system", "content": system})

        tools_payload, tool_choice = self._tool_payload(tools)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=payload_messages,
                tools=tools_payload,
                tool_choice=tool_choice,
            )
        except Exception as e:
            if tool_choice and self._is_tool_validation_error(e):
                # Fallback implementation omitted for brevity
                ...
            raise

        return self._build_message(response)
```

**Key Takeaways:**
- **Dynamic Tool Payloads:** If `tool_mode=none` is set, we bypass tools entirely. Crucial for models that hallucinatory tool schemas.
- **Graceful Fallback:** If a model invents an unsupported tool (Groq threw `tool call validation failed`), we catch it, disable tools for that turn, and rerun the query gracefully.

---

## 2. Bootstrapping the Inspector

The MCP Inspector is an invaluable web tool for testing your server without an LLM in the loop. But getting it to spin up locally over the `mcp dev` harness isn't always straightforward. 

If you use `uv` to manage environments, and the Inspector calls `mcp dev mcp_server.py`, the child Python runtime needs the right CLI tooling. 

```python
# core/server.py
from typing import Literal
import os
from mcp.server.fastmcp import FastMCP

host = os.getenv("FASTMCP_HOST", "127.0.0.1")
port = int(os.getenv("FASTMCP_PORT", 8001))

class FileSageMCP(FastMCP):
    def run(self, transport: Literal["stdio", "sse", "streamable-http"] = "sse", mount_path=None):
        super().run(transport=transport, mount_path=mount_path)

mcp = FileSageMCP(
    "FileSage",
    log_level="ERROR",
    host=host,
    port=port,
    dependencies=["typer"], # Critical for inspector sub-shells
)
```

**What went wrong here first?**
When the MCP dev watcher spins up your server, it uses `uv run --with mcp mcp run`. If your server environment lacks `typer`, the runner crashes silently, leading to `ECONNREFUSED` errors in the inspector log. Explicitly declaring `dependencies=["typer"]` fixes this. We also forced the transport default to `sse` when `run()` is triggered by the CLI.

---

## 3. Fixing Access Control Loops

In Part 2, we showed the `is_path_allowed` function. When we moved it to real environments, it crashed on generator bugs. Let's fix the directory scanning and filesystem security.

```python
# core/security.py
async def is_path_allowed(requested_path: Path, ctx: Context) -> bool:
    roots_result = await ctx.session.list_roots()
    
    if not requested_path.exists():
        check_path = requested_path.parent 
        if not check_path.exists():
            return False 
    else:
        check_path = requested_path if requested_path.is_dir() else requested_path.parent
    
    # Note: Access roots_result.roots, not the object itself
    for root in roots_result.roots:
        root_path = file_url_to_path(root.uri)
        try:
            check_path.relative_to(root_path)
            return True 
        except ValueError:
            continue
    
    return False
```

It’s small adjustments like `roots_result.roots` and `requested_path.is_dir()` that separate demo scripts from production services.

---

## 4. Managing Token Context Windows

Even on open-weight models, context isn't free. Fast APIs like Groq's LLaMA endpoints have aggressive Tokens-Per-Minute (TPM) limits. If your agentic loop runs unbounded, a single `scan_dir` tool result might blow the 6000 TPM limit of a free tier.

We engineered context truncation directly into the Chat loop:

```python
# core/chat.py
class Chat:
    def __init__(self, llm_service, clients):
        ...
        self.max_history_chars = int(os.getenv("MAX_HISTORY_CHARS", 12000))
        self.max_history_messages = int(os.getenv("MAX_HISTORY_MESSAGES", 40))

    def _truncate_history(self) -> None:
        if len(self.messages) > self.max_history_messages:
            self.messages = self.messages[-self.max_history_messages :]

        total = sum(len(str(msg.get("content", ""))) for msg in self.messages)
        if total <= self.max_history_chars:
            return

        trimmed = []
        running = 0
        for msg in reversed(self.messages):
            msg_len = len(str(msg.get("content", "")))
            if trimmed and running + msg_len > self.max_history_chars:
                break
            trimmed.append(msg)
            running += msg_len

        self.messages = list(reversed(trimmed))
```

And in the tool dispatch layer:

```python
# core/tool_manager.py 
max_result_chars = int(os.getenv("MAX_TOOL_RESULT_CHARS", 8000))
# ...
if max_result_chars > 0 and len(content) > max_result_chars:
    content = content[: max_result_chars - 15] + "...[truncated]"
```

We also added a `/reset` slash command into the CLI. If you hit a rate limit (`HTTP 413`), you type `/reset` and your agent clears its memory footprint while retaining its system instructions.

---

## Conclusion

Building FileSage MCP from a conceptually sound Host/Server/Client layout (Part 2) into this resilient, provider-agnostic engine required treating the protocol not as Magic AI Pixie Dust, but as standard distributed systems engineering. 

We:
1. Bridged the Anthropic MCP standard to OpenAI-compatible endpoints.
2. Defended against hallucinatory model payloads.
3. Stubbed out inspector environment bugs.
4. Truncated context loops to respect fast-inference rate limits.

You now have a production-ready template. 

The full code for this project is available on GitHub. View Code. 

Thanks for staying the course. As the MCP standard matures, knowing how to debug these lower-level pipeline issues is what sets you apart.