import asyncio
import sys
import os
from contextlib import AsyncExitStack
from dotenv import load_dotenv 

from mcp_client import MCPClient
from core.openai import OpenAIService
from core.cli_chat import CliChat
from core.cli import CliApp 

load_dotenv()

llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
 

async def main():
    root_paths = sys.argv[1:]
    if not root_paths:
        print("Usage: python main.py <root_dir> [additional_root_dirs...]")
        print("Example: python main.py ~/projects ~/notes")
        sys.exit(1)
 
    for path in root_paths:
        import pathlib
        if not pathlib.Path(path).exists():
            print(f"Error: path does not exist: {path}")
            sys.exit(1)
 
    if llm_provider in {"claude", "anthropic"}:
        from core.claude import Claude

        claude_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        assert anthropic_api_key, (
            "Error: ANTHROPIC_API_KEY is not set. Add it to your .env file."
        )
        llm_service = Claude(model=claude_model)
    else:
        openai_model = os.getenv("OPENAI_MODEL", "llama-3.1-8b-instant")
        openai_api_key = os.getenv("OPENAI_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
        openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
        openai_tool_mode = os.getenv("OPENAI_TOOL_MODE", "auto")
        assert openai_api_key, (
            "Error: OPENAI_API_KEY (or GROQ_API_KEY) is not set. Add it to your .env file."
        )
        llm_service = OpenAIService(
            model=openai_model,
            api_key=openai_api_key,
            base_url=openai_base_url,
            tool_mode=openai_tool_mode,
        )
 
    async with AsyncExitStack() as stack:
        # sampling_callback is passed here so ClientSession receives it
        # at construction — no private attribute patching required
        filesage_client = await stack.enter_async_context(
            MCPClient(
                command="python",
                args=["mcp_server.py"],
                roots=root_paths,
                sampling_callback=getattr(llm_service, "sampling_callback", None),
            )
        )
 
        clients = {"filesage": filesage_client}
 
        chat = CliChat(
            filesage_client=filesage_client,
            clients=clients,
            llm_service=llm_service,
        )
 
        cli = CliApp(chat)
        await cli.initialize()
        await cli.run()
 
 
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
