from core.server import mcp 

@mcp.prompt()
def summarize_file(file_path: str) -> str:
    """
    A ready-to-use prompt template for summarizing any file
    """

    return f"""Please read and summarize the file at: {file_path}

Your summary should cover:
1. What the file does and its overall purpose 
2. Key components, functions, classes, or data structures (if code)
3. Any notable patterns, potential issues, or things worth knowing
4. A one-sentence TL;DR at the very end"""

@mcp.prompt()
def code_review(file_path: str) -> str:
    """A structured code review prompt for a given file path."""
    return f"""Please perform a thorough code review of: {file_path}
 
Evaluate each of the following:
 
1. **Correctness** — Bugs, edge cases, or logical errors?
2. **Style** — Does it follow language conventions and best practices?
3. **Performance** — Any obvious bottlenecks or inefficiencies?
4. **Security** — Any vulnerabilities, unsafe inputs, or exposed secrets?
5. **Readability** — Is the code clear and well-documented?
 
Use clear headers for each section. Conclude with a prioritized list of improvements."""
 
 
@mcp.prompt()
def find_todos(directory_path: str) -> str:
    """A prompt template for hunting down TODO/FIXME/HACK comments in a directory."""
    return f"""Search the directory '{directory_path}' for all TODO, FIXME, HACK, and NOTE comments.
 
For every comment found:
- File path and line number
- The full comment text
- Priority level (FIXME = high, TODO = medium, NOTE/HACK = low)
 
Group results by file. End with a prioritized action list sorted by severity."""
 
 

