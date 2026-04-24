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
- browser_snapshot: ALWAYS pass BOTH "depth" (e.g. 3) and "filename" (e.g. "page.md") in the same call. For login pages use depth 5 or higher so text fields appear in the tree. Do not pass only "depth"—it will fail validation.
- Stale refs: every [ref=e…] is tied to a specific snapshot. After ANY navigation, click, or browser_type, the DOM and refs can change. If browser_type or browser_click says "ref not found", you MUST run browser_snapshot again and use ONLY refs from that new output—never reuse an old ref (e.g. e28) from a prior snapshot.
- Login forms: prefer browser_fill_form with a single "fields" array: fill all visible textbox fields in ONE tool call, each with type "textbox", using refs from the *same* browser_snapshot taken immediately before. That avoids the common bug of typing the email, then using an outdated ref for the password.
- If you must use two browser_type steps: (1) snapshot, (2) type email, (3) new snapshot, (4) type password with ref from step 3 only.
- browser_click: ALWAYS include "element", "ref", "doubleClick": false, "button": "left", "modifiers": [].
- Refs: use exact ids from [ref=e12] style lines in the *latest* snapshot. Never invent refs.
- If a click hit the wrong element, use browser_navigate to a direct URL instead of more bad clicks.
- browser_evaluate: only {"function": "..."} with your JS string.
LinkedIn login may use anti-bot, captchas, or iframes; automation often still cannot complete. Use /login for the form.
"""

# Cheaper / smaller context models hit OpenAI rate limits (TPM) less often for long runs.
# Compare: https://platform.openai.com/docs/models
def _openai_model() -> str:
    return (os.environ.get("OPENAI_MODEL") or "gpt-4.1").strip() or "gpt-4.1"


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=_openai_model(),
        temperature=0,
        # Helps with brief OpenAI 429 "rate limit" responses (backoff and retry)
        max_retries=6,
    )


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
            "Use browser tools only. (1) browser_navigate to https://www.linkedin.com/login . (2) browser_snapshot with depth 5+ "
            'and a filename (e.g. "login.md") so the email and password textboxes appear. (3) Prefer ONE browser_fill_form call: '
            'two "textbox" fields with name/type/ref/value, using refs for email and password from that same snapshot. '
            "(4) If you cannot get both refs in one snapshot, use browser_type for email, then a NEW browser_snapshot, "
            "then browser_type for password using only refs from the second snapshot. "
            "(5) Click submit / Sign in. "
            f"Credentials to enter: email {email!r} password {password!r}. "
            "If you see captcha, checkpoint, or ref errors after a fresh snapshot, say so and stop. Do not use Jobs until logged in."
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
            llm=_build_llm(),
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