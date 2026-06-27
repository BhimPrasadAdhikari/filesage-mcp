import os
from pathlib import Path 
from mcp.server.fastmcp import Context 
from core.utils import file_url_to_path 

async def is_path_allowed(requested_path: Path, ctx: Context) -> bool:
    """
    Check whether a path falls inside any of the client-provided roots.
    """
    try:
        roots_result = await ctx.session.list_roots()
        roots = roots_result.roots if roots_result else []
    except Exception:
        roots = []

    # Format the path we want to check
    if not requested_path.exists():
        check_path = requested_path.parent 
        if not check_path.exists():
            return False 
    else:
        check_path = requested_path if requested_path.is_dir() else requested_path.parent

    # If the client provided roots, enforce them
    if roots:
        for root in roots:
            root_path = file_url_to_path(root.uri)
            try:
                check_path.relative_to(root_path)
                return True 
            except ValueError:
                continue
        return False

    # Otherwise, fall back to ALLOWED_ROOTS environment variable
    allowed_roots_env = os.getenv("ALLOWED_ROOTS")
    if allowed_roots_env:
        if allowed_roots_env.strip() == "*":
            return True
        
        allowed_paths = [Path(p.strip()).resolve() for p in allowed_roots_env.split(",") if p.strip()]
        for root_path in allowed_paths:
            try:
                check_path.relative_to(root_path)
                return True 
            except ValueError:
                continue
        return False

    # Default secure behavior: deny if no roots are provided/configured
    return False 

