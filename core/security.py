from pathlib import Path 
from mcp.server.fastmcp import Context 
from core.utils import file_url_to_path 

async def is_path_allowed(requested_path: Path, ctx: Context) -> bool:
    """
    Check whether a path falls inside any of the client-provided roots.
    """
    roots_result = await ctx.session.list_roots()
    client_roots = roots_result.roots 

    if not requested_path.exists():
        # we check parent directory instead (for writes case)
        check_path = requested_path.parent 
        if not check_path.exists():
            return False 
    else:
        check_path = requested_path if requested_path.is_dir() else requested_path.parent
    
    for root in roots_result.roots:
        root_path = file_url_to_path(root.uri)
        try:
            check_path.relative_to(root_path)
            return True 
        except ValueError:
            continue
    
    return False 

