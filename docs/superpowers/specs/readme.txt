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