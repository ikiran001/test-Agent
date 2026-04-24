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

# Playwright MCP tools validate inputs strictly. The model must not send JSON nulls where
# the schema expects real values. These hints reduce "invalid_type" / validation errors.
_PLAYWRIGHT_TOOL_GUIDANCE = """
When you call Playwright tools, match the tool schema exactly (no nulls for required fields):
- browser_click: include "element" (string), "ref" (string from the latest snapshot), "doubleClick" (false for a normal click), "button" ("left" unless you need "right" or "middle"), and "modifiers" (use [] for none).
- browser_snapshot: prefer calling with "depth" (e.g. 2 or 3) and "filename" (e.g. "snap.md") together if you need a file; do not pass empty objects with null fields.
- browser_evaluate: use only the arguments defined for that tool (usually "function"); do not mix in other tools' fields.
If a call fails validation, fix the arguments and try again in fewer steps.
"""


def _agent_max_steps() -> int:
    return max(5, int(os.environ.get("AGENT_MAX_STEPS", "50")))


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
            "Use browser tools: open https://www.linkedin.com, Click on the sign in button, then sign in with this email and "
            f"this password, then go to the Jobs area, search for SDET jobs, and summarize "
            f"the first result (title and company). Email: {email} Password: {password}"
        )
    return (
        "Use browser tools to open https://example.com and report the visible page title."
    )


def _playwright_mcp_cmd():
    """Prefer globally installed CLI; fall back to npx.

    ``--isolated`` avoids: "Browser is already in use for ... mcp-chrome-..., use
    --isolated" when **another** Playwright MCP is running (e.g. Cursor) and
    would share the same on-disk profile. Disable with PLAYWRIGHT_MCP_NO_ISOLATED=1
    if you need the shared profile for a single known setup.
    """
    extra: list[str] = []
    if os.environ.get("PLAYWRIGHT_MCP_NO_ISOLATED", "").strip() != "1":
        extra.append("--isolated")

    path = shutil.which("playwright-mcp")
    if path:
        return path, extra
    return "npx", ["@playwright/mcp@latest", *extra]


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
            max_steps=_agent_max_steps(),
            additional_instructions=_PLAYWRIGHT_TOOL_GUIDANCE,
        )

        result = await agent.run(_build_agent_task())
        print(f"\nResult: {result}")
    finally:
        # Releases MCP + browser; avoids "browser already in use" on the next run.
        await client.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(main())