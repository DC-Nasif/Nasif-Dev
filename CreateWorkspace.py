import os
import requests
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv

# Load env variables
load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CAPACITY_ID = os.getenv("CAPACITY_ID")

FABRIC_API = "https://api.fabric.microsoft.com/v1"

def get_access_token():
    credential = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    token = credential.get_token("https://api.fabric.microsoft.com/.default")
    return token.token

def create_workspace(workspace_name):
    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "displayName": workspace_name,
        "capacityId": CAPACITY_ID
    }

    response = requests.post(
        f"{FABRIC_API}/workspaces",
        headers=headers,
        json=payload
    )

    if response.status_code in (200, 201):
        workspace = response.json()
        print(f"Workspace created successfully")
        print(f"Name : {workspace['displayName']}")
        print(f"ID   : {workspace['id']}")
        return workspace
    elif response.status_code == 409:
        print("Workspace already exists")
    else:
        print(f"Failed to create workspace")
        print(response.status_code, response.text)

if __name__ == "__main__":
    create_workspace("My Fabric Dev Workspace")
