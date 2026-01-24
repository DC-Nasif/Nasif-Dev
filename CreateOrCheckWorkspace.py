import os
import requests
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CAPACITY_ID = os.getenv("CAPACITY_ID")
WORKSPACE_NAME = os.getenv("WORKSPACE_NAME")

FABRIC_API = "https://api.fabric.microsoft.com/v1"


def get_access_token():
    credential = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    return credential.get_token(
        "https://api.fabric.microsoft.com/.default"
    ).token


def get_or_create_workspace():
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1️⃣ Check existing workspaces
    resp = requests.get(
        f"{FABRIC_API}/workspaces",
        headers=headers
    )
    resp.raise_for_status()

    for ws in resp.json().get("value", []):
        if ws["displayName"].lower() == WORKSPACE_NAME.lower():
            print(f"✅ Workspace exists: {WORKSPACE_NAME}")
            return ws["id"]

    # 2️⃣ Create workspace if not found
    payload = {
        "displayName": WORKSPACE_NAME,
        "capacityId": CAPACITY_ID
    }

    create_resp = requests.post(
        f"{FABRIC_API}/workspaces",
        headers=headers,
        json=payload
    )
    create_resp.raise_for_status()

    ws = create_resp.json()
    print(f"🆕 Workspace created: {WORKSPACE_NAME}")
    return ws["id"]


# Example run
if __name__ == "__main__":
    ws_id = get_or_create_workspace()
    print(f"Workspace ID: {ws_id}")
