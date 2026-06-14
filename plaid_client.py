import os
from pathlib import Path
from dotenv import load_dotenv
from plaid.api import plaid_api
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid import ApiClient, Configuration, Environment

# ── Config ────────────────────────────────────────────────────────────────────
# Load .env from the same directory as this file
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET    = os.getenv("PLAID_SECRET")

if not PLAID_CLIENT_ID or not PLAID_SECRET:
    raise ValueError(
        "Missing Plaid credentials. Make sure your .env file exists in the "
        "project folder and contains PLAID_CLIENT_ID and PLAID_SECRET."
    )

def get_plaid_client() -> plaid_api.PlaidApi:
    """Return an authenticated Plaid client pointed at Sandbox."""
    configuration = Configuration(
        host=Environment.Sandbox,
        api_key={
            "clientId": PLAID_CLIENT_ID,
            "secret":   PLAID_SECRET,
        },
    )
    api_client = ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def create_sandbox_access_token(client: plaid_api.PlaidApi) -> str:
    """
    Simulate a user linking their bank account in Sandbox.
    Returns a permanent access token you can reuse across runs.
    """
    # Step 1 – create a short-lived public token for the test institution
    pt_request = SandboxPublicTokenCreateRequest(
        institution_id="ins_109508",
        initial_products=[Products("transactions")],
    )
    pt_response = client.sandbox_public_token_create(pt_request)
    public_token = pt_response["public_token"]

    # Step 2 – exchange the public token for a reusable access token
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = client.item_public_token_exchange(exchange_request)
    access_token = exchange_response["access_token"]

    print(f"✅  Access token created: {access_token[:24]}…  (store this!)")
    return access_token
