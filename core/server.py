import os
from typing import Literal

from mcp.server.fastmcp import FastMCP


class FileSageMCP(FastMCP):
	def run(
		self,
		transport: Literal["stdio", "sse", "streamable-http"] = "streamable-http",
		mount_path: str | None = None,
	) -> None:
		super().run(transport=transport, mount_path=mount_path)


def _int_env(name: str, default: int) -> int:
	value = os.getenv(name)
	if not value:
		return default
	try:
		return int(value)
	except ValueError:
		return default


host = os.getenv("FASTMCP_HOST", "127.0.0.1")
port = _int_env("FASTMCP_PORT", 8001)

mcp = FileSageMCP(
	"FileSage",
	log_level="INFO",
	host=host,
	port=port,
	dependencies=["typer"],
)