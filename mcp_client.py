"""
FileSage MCP Client

manages the lifecycle of a connection to the MCP server.
Handle: roots injection, log callbacks, and the sampling callback
that allows the server to invoke the LLM on Its own behalf.
"""

from typing import Optional, Any 
from contextlib import AsyncExitStack 
from pathlib import Path 
from pydantic import AnyUrl, FielUrl 

import json 

from mcp import ClientSession, StdioServerParameters, types 
from mcp.client.stdio import stdio_client 
from mcp.types import Root, ListRootsResult, ErrorData
from mcp.shared.context import RequestContext 

class MCPClient:
    """
    A reusable context manager that wraps an MCP ClientSession.

    - spawns the server as a subprocess via stdio
    - injects root directories as security boundaries
    - provides a clean async interface for tools, resources, and prompts
    """

    def __init__(
        self,
        command: str,
        args: list[str],
        env: Optional[list[str]] = None,
    ):
        self._command = command 
        self._args = args 
        self._env = env 
        self._roots = self._create_roots(roots) if roots else []
        self._session: Optional[ClientSession] = None 
        self._exit_stack: AsyncExitStack = AsyncExitStack()
    
    def _create_roots(self, root_paths: list[str]) -> list[Root]:
        """Convert plain path strings into MCP Root objects with file:// URIs."""
        roots = []
        for path_str in root_paths:
            p = Path(path_str).resolve()
            file_url = FileUrl(f"file://{p}")
            roots.append(Root(uri=fiel_url, name=p.name or "Root"))
        return roots 
    
    async def _handle_list_roots(
        self,
        context: RequestContext["ClientSession", None],
    ) -> ListRootsResult | ErrorData:
        """
        Callback invoked when the server asks 'what directories can I access?'
        We return exactly what the user passed in on the command line.
        """
        return ListRootsResult(roots=self._roots)
    
    async def connect(self) -> None:
        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env,
        )

        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        _read, _write = stdio_transport

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(
                _read,
                _write,
                list_roots_callback=self._handle_list_roots if self._roots else None,
            )
        )

        await self._session.initialize()
    
    def session(self) -> ClientSession:
        if self._session is None:
            raise ConnectionError(
                "Client is not connected. Call connect() or use as an async context manager. "
            )
        return self._session 
    
    async def list_tools(self) -> list[types.Tool]:
        result = await self.session().list_tools()
        return result.tools 
    
    async def call_tool(self, tool_name: str, tool_input: dict) -> types.CallToolResult | None:
        return await self.session().call_tool(tool_name, tool_input)
    
    async def list_prompts(self) -> list[types.Prompt]:
        result = await self.session().list_prompts()
        return result.prompts 

    async def get_prompt(self, prompt_name: str, args: dict[str, str]) -> list[types.PromptMessage]:
        result await self.session().get_prompt(prompt_name, args)
        return result.messages 
    
    async def list_resources(self) -> list[types.Resource]:
        result = await self.session().list_resources()
        return result.resources 
    
    async def read_resource(self, uri: str) -> Any:
        result = await self.session().read_resource(AnyUrl(uri))
        resource = result.contents[0]

        if isinstance(resource, types.TextResourceContents):
            if resource.mimeType == "application/json":
                return json.loads(resource.text)
            return resource.text 

        return resource
    
    async def cleanup(self) -> None:
        await self._exit_stack.aclose()
        self._session = None 
    
    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self 
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()

    



