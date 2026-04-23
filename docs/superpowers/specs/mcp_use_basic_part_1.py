import asyncio
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

# Load OPENAI_API_KEY from .env next to this script
load_dotenv(Path(__file__).resolve().parent / ".env")


def _playwright_mcp_cmd():
    """Prefer globally installed CLI; fall back to npx."""
    path = shutil.which("playwright-mcp")
    if path:
        return path, []
    return "npx", ["@playwright/mcp@latest"]


async def main():
    cmd, args = _playwright_mcp_cmd()
    # macOS/Windows: no Linux DISPLAY override
    mcp_server: dict = {"command": cmd, "args": args}
    if os.name == "posix" and "DISPLAY" in os.environ:
        mcp_server["env"] = {"DISPLAY": os.environ["DISPLAY"]}

    client = MCPClient(
        {
            "mcpServers": {
                "playwright": mcp_server,
            }
        }
    )

    agent = MCPAgent(
        llm=ChatOpenAI(model="gpt-4.1", temperature=0),
        client=client,
        max_steps=15,
    )

    # Shorter, reliable smoke: fetch a page title (avoids Google captcha blocks)
    result = await agent.run(
        "Use browser tools to open https://example.com and report the visible page title."
    )

    print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())