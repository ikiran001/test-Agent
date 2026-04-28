1. Install Python (3.10+)
Check:
python3 --version


✅ 2. Install Node.js (Required for MCP / Playwright)
Download: https://nodejs.org
Check:
node -v
npm -v


✅ 3. Install Python Dependencies
pip3 install langchain-openai mcp-use


✅ 4. Install Playwright MCP
npm install -g @playwright/mcp


✅ 5. Set OpenAI API Key
Mac/Linux:
export OPENAI_API_KEY=your_key
Windows:
setx OPENAI_API_KEY "your_key"


✅ 6. (Optional) Create Virtual Environment
python3 -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows


✅ 7. Hosted UI verification — headed browser (visible window while the agent runs)
• Copy `.env.example` to `.env` and set OPENAI_API_KEY; for UI verify set USE_UI_VERIFY=1, APP_LOGIN_URL, APP_HOSTING_VERIFY_URL. Credentials: **HOSTING_EMAIL** / **HOSTING_PASSWORD** (preferred for Hosting login), or APP_*, or LINKEDIN_* as fallbacks. URLs may use BLUEHOST_* aliases.
• Visible browser is the default. Set PLAYWRIGHT_MCP_HEADLESS=1 only if you truly need invisible headless runs.
• From this folder: USE_UI_VERIFY=1 python3 mcp_use_basic_part_1.py
• Values used in login can reach your LLM provider — use disposable test accounts only.