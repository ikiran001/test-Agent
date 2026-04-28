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
- browser_fill_form: each field "type" MUST be `textbox` exactly.
- browser_snapshot: include "depth" and "filename". On Bluehost login use depth **10–12** after overlays so textbox lines appear in YAML.
- **browser_click** must include ALL of: **element** (human description string), **ref** (snapshot ref like `e104`, NOT a CSS string in ref), **selector** (CSS OR use ref with selector per server rules), **doubleClick** boolean, **button** one of `left`|`right`|`middle`, **modifiers** JSON array (often `[]`).
  To click "Got It" cookie button from snapshot line `- button "Got It" [ref=e104]`: use element `Got It`, ref `e104`, doubleClick `false`, button `left`, modifiers `[]`. If your server requires selector with ref `_`, use selector `button:has-text("Got It")` ref `_` with the same doubleClick/button/modifiers.
- Alternatively dismiss cookies with **browser_run_code** (must include **filename** string, e.g. `cookie.js`, plus **code** body): `async (page) => { await page.getByRole('button', { name: 'Got It' }).click({ timeout: 3000 }).catch(() => {}); }`
- **browser_wait_for**: if the tool requires text/textGone strings, do NOT pass only time — use **browser_run_code** `async (page) => { await page.waitForTimeout(3000); }` for a plain pause (or wait for selector).
- **browser_type:** pass **element**, **ref** from snapshot (e.g. textbox `e200`), **text**, **submit** boolean, **slowly** boolean — never null.
- Bluehost: click **Hosting Login** tab before fields if Webmail is active — look for `Hosting Login` in snapshot and click that ref with full browser_click fields.
- Cookie / tabs / navigation: take a **new snapshot** after each action.
- LinkedIn-style selector fallback order for generic sites remains: session_key, autocomplete, etc., then fill_form.
- browser_evaluate: page-only `{"function": "() => {}"}`.
- linkedin.com/jobs: first job card in left list.
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


def _env_first_nonempty(*keys: str) -> str:
    for k in keys:
        raw = os.environ.get(k)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            return s
    return ""


def _credential_password(primary: str, fallback: str) -> str:
    """Prefer primary env password; fallback if primary missing."""
    if primary in os.environ and os.environ[primary]:
        return str(os.environ[primary])
    if fallback in os.environ and os.environ[fallback]:
        return str(os.environ[fallback])
    return ""


def _credential_any(*keys: str) -> str:
    """First non-empty password-like value from listed env keys."""
    for k in keys:
        if k in os.environ and str(os.environ[k]).strip():
            return str(os.environ[k])
    return ""


def _build_agent_task() -> str:
    """Build the user task string from env. Source code must stay credential-free.

    Security:
    - Storing email/password in **.env** keeps them out of **git** (good).
    - If you put the password *inside* the string passed to `agent.run()`, the **LLM
      provider (OpenAI)** can receive, process, and log it. Do not use real account
      passwords for production-style automation. Prefer a safe smoke test, or log in
      manually and keep tasks to post-login steps only.
    """
    if os.environ.get("USE_UI_VERIFY", "0").strip() == "1":
        login_url = _env_first_nonempty("APP_LOGIN_URL", "BLUEHOST_LOGIN_URL")
        hosting_url = _env_first_nonempty("APP_HOSTING_VERIFY_URL", "BLUEHOST_HOSTING_URL")
        email = _env_first_nonempty(
            "HOSTING_EMAIL",
            "HOTING_EMAIL",  # common typo
            "APP_EMAIL",
            "LINKEDIN_EMAIL",
            "hosting_email",  # allow lowercase .env keys
        )
        password = _credential_any(
            "HOSTING_PASSWORD",
            "APP_PASSWORD",
            "LINKEDIN_PASSWORD",
            "hosting_password",
        )
        missing: list[str] = []
        if not login_url:
            missing.append("APP_LOGIN_URL (or BLUEHOST_LOGIN_URL)")
        if not hosting_url:
            missing.append("APP_HOSTING_VERIFY_URL (or BLUEHOST_HOSTING_URL)")
        if not email:
            missing.append("HOSTING_EMAIL (or APP_EMAIL or LINKEDIN_EMAIL)")
        if not password:
            missing.append("HOSTING_PASSWORD (or APP_PASSWORD or LINKEDIN_PASSWORD)")
        if missing:
            raise SystemExit(
                "USE_UI_VERIFY=1 is missing: " + ", ".join(missing) + ". See .env.example."
            )
        return (
            "Use browser tools only — verify Hosting UI; headed browser. Order: "
            "(A) browser_navigate "
            f"{login_url!r}. "
            "(B) browser_snapshot depth 11 filename hosting-s1.yaml. "
            "(C) Cookie dialog: **browser_click** `Got It` using full args (element text, ref e106 or line from YAML, "
            "doubleClick false, button left, modifiers []) OR selector `role=dialog >> button:has-text(\\\"Got It\\\")` ref `_`. "
            "Snapshot hosting-s2.yaml. "
            "(D) Click **Hosting Login** tab if needed (ref from YAML). Snapshot hosting-s3.yaml. "
            "(E) Bluehost labels the first field **User ID** — use textbox refs from YAML (often e47 and e51 for password). "
            f"Put {email!r} in User ID and password {password!r} in Password. browser_type: submit=false slowly=false. "
            "(F) Click **Login** when enabled (snapshot ref); MFA/CAPTCHA ⇒ stop and describe. "
            "(G) browser_navigate "
            f"{hosting_url!r}. "
            "(H) browser_snapshot depth 11 filename hosting-dash.yaml; summarize Hosting headings/nav/alerts only from YAML."
        )
    if os.environ.get("USE_LINKEDIN_DEMO", "0").strip() == "1":
        email = (os.environ.get("LINKEDIN_EMAIL") or "").strip()
        password = os.environ.get("LINKEDIN_PASSWORD") or ""
        if not email or not password:
            raise SystemExit(
                "USE_LINKEDIN_DEMO=1 requires LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env"
            )
        return (
            "Use browser tools only. LinkedIn may show different login UIs; handle variants. "
            "(1) browser_navigate to https://www.linkedin.com/checkpoint/rm/sign-in-another-account?fromSignIn=true&trk=guest_homepage-basic_nav-header-signin . "
            "(2) browser_fill_form: two fields, each with type textbox (exactly), ref \"_\", and a selector. "
            f"Values: email {email!r}, password {password!r}. "
            "If first selectors fail, retry fill_form with the next pair from the system instructions (#username, then session_key, then autocomplete, then type=email/password in main). "
            "(3) If every selector says no elements, one browser_snapshot (depth 6-8) then browser_type each field using refs from `textbox` lines only. "
            "(4) Submit: browser_click with a non-empty selector, e.g. `button[type=\"submit\"]`, and ref \"_\" plus doubleClick false, button left, modifiers []. Or browser_press_key Enter. "
            "Never use only ref \"_\" without selector on browser_click. Never increase snapshot depth above 10. Stop on captcha. "
            "After successful login, you MUST: "
            "(5) Go to https://www.linkedin.com/jobs/ . "
            "(6) In the main job search box, search for *SDET* (use browser_snapshot; try selectors like input.jobs-search-box__text-input, or textbox refs from the snapshot), then run the search. "
            "(7) In the *left* job results list, open the **first** real job (top item—the first job **title** / card in the list, not an ad or promo). Use snapshot for refs, then click. "
            "(8) On that job’s page only, use **Apply** or **Easy Apply** and continue that application until submitted or blocked. Do not pick a different job—the goal is the **very first** job in the list after the search. "
            "If there is no Easy Apply, say so and stop."
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
    # Default is HEADED (visible browser). Set PLAYWRIGHT_MCP_HEADLESS=1 only for unattended runs.
    if os.environ.get("PLAYWRIGHT_MCP_HEADLESS", "").strip() == "1":
        extra.append("--headless")

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
    if os.environ.get("USE_UI_VERIFY", "").strip() == "1":
        # Login + cookie/tab handling + dashboard needs more tool rounds than default.
        os.environ.setdefault("AGENT_MAX_STEPS", "80")

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