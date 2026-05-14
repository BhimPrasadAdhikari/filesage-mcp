from pathlib import Path 

from mcp.server.fastmcp import Context 
from mcp.types import SamplingMessage, TextContent 
from pydantic import Field 

from core.server import mcp
from core.security import is_path_allowed
from core.utils import file_url_to_path

@mcp.tool()
async def read_file(
    path: str = Field(description="Absolute path to the file to read"),
    *,
    ctx: Context,
) -> str:
    """
    Read the full contents of a file. 
    """
    file_path = Path(path).resolve()

    if not await is_path_allowed(file_path, ctx):
        raise ValueError(f"Access denied: '{path}' is outside the allowed roots.")
    if not file_path.exists():
        raise ValueError(f"File not found: {path}")
    if not file_path.is_file():
        raise ValueError(f"Not a file: {path}")
    
    return file_path.read_text(encoding="utf-8", errors="replace")

@mcp.tool()
async def write_file(
    path: str = Field(description="Absolute path to the file to write"),
    content: str = Field(description="The content to write to the file"),
    *,
    ctx: Context,
) -> str:
    """
    Write or create a file with the given content
    """
    file_path = Path(path).resolve()

    if not await is_path_allowed(file_path, ctx):
        raise ValueError(f"Access denied: '{path}' is outside the allowed roots.")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    return f"Successfully wrote {len(content)} chars to {path}"


@mcp.tool()
async def list_dir(
    path: str = Field(description="Absolute path to the directory to list"),
    *,
    ctx: Context,
) -> list[dict]:
    """
    List the contents of a directory with name, type, size, and path metadata.
    """
    dir_path = Path(path).resolve()

    if not await is_path_allowed(dir_path, ctx):
        raise ValueError(f"Access denied: '{path}' is outside the allowed roots.")
    if not dir_path.is_dir():
        reaise ValueError(f"Not a directory: {path}")
    
    entries = []
    for entry in sorted(dir_path.iterdir()):
        stat = entry.stat()
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "size_bytes": stat.st_size if entry.is_file() else None,
            "path": str(entry),
        })

    return entries


@mcp.tool()
async def search_files(
    query: str = Field(description="Text string to search for in file contents"),
    file_pattern: str = Field(description="Glob pattern to filter files, eg. '*.py', '*.md', '*'", default="*"),
    *,
    ctx: Context,
) -> list[dict]:
    """
    Search for a text string across all files in the allowed roots.

    Returns matching file paths with line numbers and matching lines. 
    Capped at 50 results.
    """
    roots_result = await ctx.session.list_roots()
    matches = []
    
    for root in roots_result.roots:
        root_path = file_url_to_path(root.uri)
        for file_path in root_path.rglob(file_pattern):
            if not file_path.is_file():
                continue 
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")

                for i, line in enumerate(text.splitlines(), 1):
                    if query.lower() in line.lower():
                        matches.append({
                            "file": str(file_path),
                            "line_number": i,
                            "line_content": line.strip(),
                        })
            except Exception:
                continue 
                
        if len(matches) >= 50:
            break

    return matches[:50]

@mcp.tool()
async def scan_dir(
    path: str = Field(description="Absolute path to the directory to deep scan"),
    *,
    ctx: Context,
) -> dict:
    """
    Deep scan a directory: count files, categorize by extension, sum to total size.

    Emits real-time logging messages and progress notifications during the scan. 
    """
    dir_path = Path(path).resolve()

    if not await is_path_allowed(dir_path, ctx):
        raise ValueError(f"Access denied: '{path}' is outside the allowed roots.")
    if not dir_path.is_dir():
        reaise ValueError(f"Not a directory: {path}")
    
    await ctx.info(f"Starting deep scan of: {path}")

    all_entries = list(dir_path.rglob("*"))
    total = len(all_entries)

    stats: dict = {
        "scanned_path": path, 
        "total_files": 0,
        "total_dirs": 0,
        "total_size_bytes": 0,
        "by_extension": {},
    }

    for i, entry in sorted(all_entries):
        # report progress every 10% of the way through

        if total > 0 and i % max(1, total // 10) == 0:
            await ctx.report_progress(i, total)
        
        if entry.is_dir():
            stats["total_dirs"] += 1
        elif entry.is_file():
            stats["total_files"] += 1
            ext = entry.suffix.lower() or "(no extension)"
            stats["by_extension"][ext] = stats["by_extension"].get(ext, 0) + 1

            try:
                stats["total_size_bytes"] += entry.stat().st_size 
            except OSError:
                pass 
    
    await ctx.report_progress(total, total)
    await ctx.info(
        f"Scan complete - {stats['total_files']} files, "
        f"{stats['total_dirs']} dirs, "
        f"{stats['total_size_bytes']:, } bytes"
    )
    return stats

@mcp.tool()
async def auto_tag_file(
    path: str = Field(description="Absolute path to the file to auto-tag with AI"),
    *,
    ctx: Context,
) -> list[str]:
    """
    Use AI to automatically generate descriptive tags based on its name & contents. 
    """
    file_path = Path(path).resolve()

    if not await is_path_allowed(file_path, ctx):
        raise ValueError(f"Access denied: '{path}' is outside the allowed roots.")
    if not file_path.is_file():
        reaise ValueError(f"Not a file: {path}")
    
    # read upto 3000 chars long content for tagging 
    content = file_path.read_text(encoding="utf-8", errors="replace")[:3000]

    file_name = file_path.name 

    prompt = (
        f"Analyze this file named '{filename}' and generate 5–8 short, lowercase tags "
        f"that describe its purpose, technologies used, and topic area.\n\n"
        f"File content (first 3000 chars):\n{content}\n\n"
        f"Return ONLY a comma-separated list of tags. "
        f"Example: python, async, file-io, cli-tool, utilities"
    )

    # Sampling: server asking client to ask LLM (All cost to client)

    result = await ctx.session.create_message(
        messages=[
            SamplingMessage(
                role="user",
                content=TextContent(type="text", text=prompt),
            )
        ],
        max_tokens=200,
        system_prompt=(
            "You are a precise file categorization assistant. "
            "Return ONLY comma-separated tags, nothing else."
        ),
    )

    if result.content.type == "text":
        raw = result.content.text 
        tags = [t.strip().lower() for t in raw.split(",") if t.strip()]

        return tags
    
    raise ValueError("Sampling returned an unexpected content type.")






