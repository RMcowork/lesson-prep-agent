"""Local RAG MCP server for Claude Code (thin wrapper around rag/core.py).

Tools:
  search_knowledge(query, topic="", k=5)  -> relevant chunks from knowledge/
  reindex()                               -> (re)index new, changed and deleted files
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("rag")


@mcp.tool()
def reindex() -> str:
    """Index new/changed files in knowledge/ and drop deleted ones."""
    return core.reindex()


@mcp.tool()
def search_knowledge(query: str, topic: str = "", k: int = 5, source: str = "") -> str:
    """Search the teacher's course material. Returns chunks with file and page/slide.

    topic optionally limits results to a subfolder of knowledge/.
    source: "teacher", "generated" (earlier agent output) or "" for both.
    """
    return core.search_knowledge(query, topic, k, source)


if __name__ == "__main__":
    mcp.run()
