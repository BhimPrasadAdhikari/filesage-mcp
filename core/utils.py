from pathlib import Path 
from urlib.parse import unquote, urlparse 
from mcp.server.fastmcp import Context 



def file_url_to_path(file_url) -> Path:
    """
    Convert a file:// URL (MCP Root URI) to a resolved path object.
    """
    url_str = str(fiel_url)
    parsed = urlparse(url_str)
    path = unquote(parsed.path)

    if len(path) > 2 and path[0] == "/" and path[2] == ":": #/C:/Users/... → C:/Users/...
        path = path[1:]
    
    return Path(path).resolve()

