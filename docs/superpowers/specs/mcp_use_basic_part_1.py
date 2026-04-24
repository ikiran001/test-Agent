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
- browser_fill_form: each field "type" MUST be the exact string `textbox` (never "text" or "Text" — that causes validation errors).
- browser_snapshot: always include "depth" and "filename". Use depth **between 4 and 10 only** on login pages. Do not raise depth past 10 (e.g. 100) — that wastes tokens and does not fix missing selectors.
- LinkedIn A/B and layout changes: `input#username` may not exist in the DOM. Try **in order** (same fill_form, new attempt), each with ref "_" and type textbox: (1) `input#username` / `input#password` (2) `input[name="session_key"]` / `input[name="session_password"]` (3) `input[autocomplete="username"]` / `input[autocomplete="current-password"]` (4) `input[type="email"]` / `input[type="password"]` inside `main` if present: `main input[type=email]`, `main input[type=password]`. (5) If all selectors "match no elements", take **one** snapshot (depth 6-8) and use **browser_type** with the **ref** for each `textbox` line (Email/Password) from that snapshot, not a guessed ref.
- browser_click: If using ref "_" as a placeholder, you MUST set a non-empty "selector" (CSS). If "selector" is empty or missing, the server treats ref "_" as a real aria ref and it **fails**. Example: `selector` `button[type="submit"]`, `ref` `_`, plus doubleClick false, button left, modifiers [].
- Click the **button** "Sign in", not the H1 "Sign in" heading. Submit fallback: `browser_press_key` with "Enter" after focus on password, or `browser_run_code` with `async (page) => { await page.locator('button[type=submit]').first().click(); }` if allowed.
- browser_evaluate: page-level only: {"function": "() => { ... }"} — do not add null element/ref/filename.
- Stale refs: new snapshot after navigation before ref-based actions.
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
            "Use browser tools only. LinkedIn may show different login UIs; handle variants. "
            "(1) browser_navigate to https://www.linkedin.com/login/ . "
            "(2) browser_fill_form: two fields, each with type textbox (exactly), ref \"_\", and a selector. "
            f"Values: email {email!r}, password {password!r}. "
            "If first selectors fail, retry fill_form with the next pair from the system instructions (#username, then session_key, then autocomplete, then type=email/password in main). "
            "(3) If every selector says no elements, one browser_snapshot (depth 6-8) then browser_type each field using refs from `textbox` lines only. "
            "(4) Submit: browser_click with a non-empty selector, e.g. `button[type=\"submit\"]`, and ref \"_\" plus doubleClick false, button left, modifiers []. Or browser_press_key Enter. "
            "Never use only ref \"_\" without selector on browser_click. Never increase snapshot depth above 10. Stop on captcha."
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