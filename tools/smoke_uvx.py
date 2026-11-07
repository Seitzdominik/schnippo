"""Does the built package start the way users start it? uvx from the wheel, MCP handshake, list tools."""
import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main(wheel: str) -> None:
    env = {k: v for k, v in os.environ.items() if k != "GLADIA_API_KEY"} | {"SCHNIPPO_UPDATE_CHECK": "0", "SCHNIPPO_NO_MIGRATE": "1"}
    params = StdioServerParameters(command="uvx", args=["--isolated", "--from", str(Path(wheel).resolve()), "schnippo"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            info = await s.initialize()
            tools = await s.list_tools()
            print(info.server_info.name, info.server_info.version, f"{len(tools.tools)} Tools")
            assert len(tools.tools) > 40


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
