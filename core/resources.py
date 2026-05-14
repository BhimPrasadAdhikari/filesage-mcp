from pathlib import Path 
from mcp.server.fastmcp import Context 

from core.server import mcp 

from core.utils import file_url_to_path
from core.security import is_path_allowed

@mcp.resource("files://roots")
async def get_roots(ctx: Context) -> str:
    """
    List all root directories that this server is allowed to access. 

    Read this resource first to uderstand the available filesystem scope.
    """
    roots_result = await ctx.session.list_roots()
    if not roots_result.roots:
        return "No root directories have been configured"
    
    lines = ["Allowed roots:"]
    for root in roots_result.roots:
        root_path = file_url_to_path(root.uri)
        lines.append(f" {root.name}: {root_path}")

    return "\n".join(lines)

@mcp.resource("files://tree/{path}")
async def get_tree(path: str, ctx: Context) -> str:
    """
    Return a visual ASCII directory tree for a given path.
    Limited to 3 levels deep to keep the output readable.
    Access via: files://tree//absolute/path/to/dir
    """
    dir_path = Path(path).resolve()
 
    if not await is_path_allowed(dir_path, ctx):
        raise ValueError(f"Access denied: '{path}'")
    if not dir_path.is_dir():
        raise ValueError(f"Not a directory: '{path}'")
 
    def build_tree(p: Path, prefix: str = "", depth: int = 0) -> list[str]:
        if depth > 3:
            return [f"{prefix}... (truncated)"]
        lines = []
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return [f"{prefix}[permission denied]"]
 
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                ext_prefix = "    " if is_last else "│   "
                lines.extend(build_tree(entry, prefix + ext_prefix, depth + 1))
        return lines
 
    tree_lines = [str(dir_path)] + build_tree(dir_path)
    return "\n".join(tree_lines)
 

