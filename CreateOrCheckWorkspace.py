import os
import requests
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CAPACITY_ID = os.getenv("CAPACITY_ID")
PROD_PROD_WORKSPACE_NAME = os.getenv("PROD_PROD_WORKSPACE_NAME")

FABRIC_API = "https://api.fabric.microsoft.com/v1"


def get_access_token():
    """Get Azure AD access token for Fabric API"""
    credential = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    return token

def get_or_create_workspace(PROD_WORKSPACE_NAME):
    """
    Check if Fabric workspace exists by name.
    If not, create it.
    Always return workspace ID.
    """

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1️ Check existing workspaces
    resp = requests.get(
        f"{FABRIC_API}/workspaces",
        headers=headers
    )
    resp.raise_for_status()

    for ws in resp.json().get("value", []):
        if ws["displayName"].lower() == PROD_WORKSPACE_NAME.lower():
            print(f"Workspace exists: {PROD_WORKSPACE_NAME}")
            return ws["id"]

    # 2️ Create workspace if not found
    payload = {
        "displayName": PROD_WORKSPACE_NAME,
        "capacityId": CAPACITY_ID
    }

    create_resp = requests.post(
        f"{FABRIC_API}/workspaces",
        headers=headers,
        json=payload
    )
    create_resp.raise_for_status()

    ws = create_resp.json()
    print(f"Workspace created: {PROD_WORKSPACE_NAME}")
    return ws["id"]


# Example usage
if __name__ == "__main__":
    ws_id = get_or_create_workspace()
    print(f"Workspace ID: {ws_id}")
