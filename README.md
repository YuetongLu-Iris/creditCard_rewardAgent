# creditCard_rewardAgent
Building a credit card reward agent to maximize the rewards

## Setup

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your API keys:
   - Plaid: https://dashboard.plaid.com
   - Anthropic: https://console.anthropic.com
3. Create a virtual environment and install dependencies:
   pip install -r requirements.txt
4. Run the backend:
   uvicorn main:app --reload
5. Run the frontend:
   cd frontend && npm install && npm run dev
