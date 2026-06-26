"""
Extends the base Chat loop with:
- Access to the filesage client for prompts and resources
- Sampling is wired at the MCPClient level (passed into ClientSession
  at construction)
"""

from core.chat import Chat
from mcp_client import MCPClient


class CliChat(Chat):

    def __init__(
        self,
        filesage_client: MCPClient,
        clients: dict[str, MCPClient],
        llm_service,
    ):
        super().__init__(clients=clients, llm_service=llm_service)
        self.filesage_client = filesage_client

    async def list_prompts(self):
        return await self.filesage_client.list_prompts()

    async def list_resources(self):
        return await self.filesage_client.list_resources()

    async def get_prompt(self, name: str, args: dict[str, str]):
        return await self.filesage_client.get_prompt(name, args)

    async def read_resource(self, uri: str):
        return await self.filesage_client.read_resource(uri)