from pathlib import Path
from urllib.parse import unquote, urlparse
from mcp.server.fastmcp import Context

def file_url_to_path(file_url) -> Path:
    """
    Convert a file:// URL (MCP Root URI) to a resolved path object.
    """
    url_str = str(file_url)
    parsed = urlparse(url_str)
    path = unquote(parsed.path)

    if len(path) > 2 and path[0] == "/" and path[2] == ":": #/C:/Users/... â†’ C:/Users/...
        path = path[1:]
    
    return Path(path).resolve()

async def resolve_tool_path(path_str: str, ctx: Context) -> Path:
    """
    Resolve a potentially relative path against the available workspace roots.
    """
    p = Path(path_str)
    if p.is_absolute():
        return p.resolve()
        
    roots_result = await ctx.session.list_roots()
    
    candidate = None
    # 1. Check if the relative path exists inside any of the roots
    for root in roots_result.roots:
        root_path = file_url_to_path(root.uri)
        test_path = root_path / p
        if test_path.exists():
            return test_path.resolve()
            
        # Store the first root path as a fallback candidate for creating NEW files
        if not candidate:
            candidate = test_path.resolve()
            
    # 2. If it doesn't exist anywhere, but we have roots, assume the user
    #    wants to create the file in the first available root.
    if candidate:
        return candidate
        
    return p.resolve()


