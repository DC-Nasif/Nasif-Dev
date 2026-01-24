import os
import sys
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

access_token = None
workspace_id = None

def get_access_token():
    try:
        credential = ClientSecretCredential(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        )
        token = credential.get_token(
            "https://api.fabric.microsoft.com/.default"
            ).token
        global access_token
        access_token = token
        print("[OK] Access token generated successfully")
        return access_token
    except Exception as e:
        print(f"[ERROR] Error generating access token: {e}")
        raise e


def get_headers():
    """Return authorization headers"""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }


def verify_service_principal_access():
    """Verify SP can access Fabric API"""
    try:
        url = f"{FABRIC_API}/workspaces"
        response = requests.get(url, headers=get_headers())
        
        if response.status_code == 200:
            workspaces = response.json().get("value", [])
            print(f"[OK] Service Principal authenticated. Found {len(workspaces)} workspace(s)")
            return True
        elif response.status_code == 401:
            print("[ERROR] Authentication failed - invalid credentials")
            return False
        elif response.status_code == 403:
            print("[WARNING] Authenticated but no workspace access - permissions needed")
            return False
    except Exception as e:
        print(f"[ERROR] Access verification failed: {e}")
        return False


def get_or_create_workspace():
    # token = get_access_token()

    # headers = {
    #     "Authorization": f"Bearer {token}",
    #     "Content-Type": "application/json"
    # }

    # 1️ Check existing workspaces
    get_response = requests.get(
        f"{FABRIC_API}/workspaces", 
        headers=get_headers()
    )
    get_response.raise_for_status()

    for ws in get_response.json().get("value", []):
        if ws["displayName"].lower() == WORKSPACE_NAME.lower():
            global workspace_id
            workspace_id = ws['id']
            print(f"Workspace exists: {WORKSPACE_NAME}")
            print(f"Workspace ID: {workspace_id}")
            print("[OK] Workspace ID retrieved successfully")
            return workspace_id

    # 2️ Create workspace if not found
    payload = {
        "displayName": WORKSPACE_NAME,
        "capacityId": CAPACITY_ID
    }

    post_response = requests.post(
        f"{FABRIC_API}/workspaces",
        headers=get_headers(),
        json=payload
    )
    post_response.raise_for_status()

    ws = post_response.json()
    print(f"Workspace created: {WORKSPACE_NAME}")
    return ws["id"]


def main():
    print("\n=== Microsoft Fabric Deployment ===\n")
    
    # Step 1: Get token
    print("--- Get Fabric Access Token ---")
    get_access_token()
    
    # Step 2: Verify Service Principal access
    print("--- Verifying Authentication ---")
    if not verify_service_principal_access():
        print("[FATAL] Service Principal cannot access Fabric API")
        return
    
    # Step 3: Create/verify workspace
    print("\n--- Workspace Setup ---")    
    get_or_create_workspace()
    
     
if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"Deployment failed: {ex}")
        sys.exit(1)