import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp_use import MCPAgent, MCPClient

# Load secrets from .env next to this script (keep .env out of git; see .env.example)
load_dotenv(Path(__file__).resolve().parent / ".env")


def _build_agent_task() -> str:
    """Build the user task string from env. Source code must stay credential-free.

    Security:
    - Storing email/password in **.env** keeps them out of **git** (good).
    - If you put the password *inside* the string passed to `agent.run()`, the **LLM
      provider (OpenAI)** can receive, process, and log it. Do not use real account
      passwords for production-style automation. Prefer a safe smoke test, or log in
      manually and keep tasks to post-login steps only.
    """
    if os.environ.get("USE_LINKEDIN_DEMO", "0").strip() == "1":
        email = (os.environ.get("LINKEDIN_EMAIL") or "").strip()
        password = os.environ.get("LINKEDIN_PASSWORD") or ""
        if not email or not password:
            raise SystemExit(
                "USE_LINKEDIN_DEMO=1 requires LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env"
            )
        return (
            "Use browser tools: open https://www.linkedin.com, sign in with this email and "
            f"this password, then go to the Jobs area, search for SDET jobs, and summarize "
            f"the first result (title and company). Email: {email} Password: {password}"
        )
    return (
        "Use browser tools to open https://example.com and report the visible page title."
    )


def _playwright_mcp_cmd():
    """Prefer globally installed CLI; fall back to npx."""
    path = shutil.which("playwright-mcp")
    if path:
        return path, []
    return "npx", ["@playwright/mcp@latest"]


def _kill_stale_playwright_mcp() -> None:
    """If MCP_KILL_STALE_PLAYWRIGHT=1, end leftover node/playwright-mcp from crashed runs.

    Do not set this if you run Playwright MCP from Cursor at the same time.
    """
    if os.name == "nt" or os.environ.get("MCP_KILL_STALE_PLAYWRIGHT", "").strip() != "1":
        return
    pkill = shutil.which("pkill")
    if not pkill:
        return
    subprocess.run([pkill, "-f", "playwright-mcp"], check=False, capture_output=True)
    time.sleep(1.0)


async def main():
    _kill_stale_playwright_mcp()

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

    try:
        agent = MCPAgent(
            llm=ChatOpenAI(model="gpt-4.1", temperature=0),
            client=client,
            max_steps=15,
        )

        result = await agent.run(_build_agent_task())
        print(f"\nResult: {result}")
    finally:
        # Releases MCP + browser; avoids "browser already in use" on the next run.
        await client.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(main())