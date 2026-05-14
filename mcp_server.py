import sys 
from core.server import mcp 

import core.tools 
import core.resources
import core.prompts 

if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "sse":
        mcp.run(transport="sse",host=0.0.0.0, port=8000)
    else:
        mcp.run(transport="stdio")