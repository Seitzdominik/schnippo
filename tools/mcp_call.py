"""Call one schnippo MCP tool over stdio like a client would; print text, save images.

  uv run python tools/mcp_call.py <tool> '<json args>' [outdir]
  JSON values starting with @ are read from a file: '{"cutlist": "@meine_cutlist.json"}'
"""

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main(tool: str, args: dict, outdir: Path) -> None:
    for k, v in list(args.items()):
        if isinstance(v, str) and v.startswith("@"):
            args[k] = json.loads(Path(v[1:]).read_text(encoding="utf-8"))
    params = StdioServerParameters(command="uv", args=["run", "schnippo"], env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            n = 0
            for c in res.content:
                if getattr(c, "type", "") == "image":
                    n += 1
                    outdir.mkdir(parents=True, exist_ok=True)
                    f = outdir / f"{tool}_{n}.{getattr(c, 'mime_type', 'image/jpeg').split('/')[-1]}"
                    f.write_bytes(base64.b64decode(c.data))
                    print(f"[Bild {n}: {f} · {len(base64.b64decode(c.data)) // 1024} KB]")
                else:
                    print(getattr(c, "text", c))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {},
                     Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).parent / "out" / "mcp"))
