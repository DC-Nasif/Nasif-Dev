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

roles = [
    {
        "role_name": "Admin",
        "users": [
            "c8bbc001-4cfc-4041-897d-949857474f4f"
        ]
    }
]

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
        print("Access token:", access_token)
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
    # 1️ Check existing workspaces
    get_ws_response = requests.get(
        f"{FABRIC_API}/workspaces", 
        headers=get_headers()
    )
    get_ws_response.raise_for_status()

    for ws in get_ws_response.json().get("value", []):
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


def get_workspace_users():
    response = requests.get(
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/users",
        headers=get_headers()
    )
    response.raise_for_status()
    print(f"Users in workspace {WORKSPACE_NAME}: {response.json().get("value", [])}")
    return response.json().get("value", [])

def get_token(scope):
    try:
        credential = ClientSecretCredential(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        )
        token = credential.get_token(scope).token
        print(f"[OK] Token generated for scope: {scope}")
        return token
    except Exception as e:
        print(f"[ERROR] Token generation failed: {e}")
        raise

    
    # token = credential.get_token(scope)
    # return token.token

def get_graph_headers():
    token = get_token("https://graph.microsoft.com/.default")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_fabric_headers():
    token = get_token("https://api.fabric.microsoft.com/.default")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }




# def get_user_object_id(email):
#     url = f"https://graph.microsoft.com/v1.0/users/{email}"
#     response = requests.get(url, headers=get_headers())
#     response.raise_for_status()
#     print(response.json()["id"])
#     return response.json()["id"]


def get_user_object_id(email):
    url = f"https://graph.microsoft.com/v1.0/users/{email}"
    response = requests.get(url, headers=get_graph_headers())
    response.raise_for_status()
    print("User Object ID:", response.json()["id"])
    return response.json()["id"]






# def get_role_assignments():
#     get_role_response = requests.get(
#         f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments", 
#         headers=get_headers()
#         )
#     get_role_response.raise_for_status()
#     return get_role_response.json().get("value", [])


# def assign_roles(roles):
#     # headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
#     existing = {(ra["principal"]["id"], ra["role"]) for ra in get_role_assignments()}
 
#     for role in roles:
#         role_name = role["role_name"]
#         for user_id in role.get("users", []):
#             if (user_id, role_name) in existing:
#                 print(f"[SKIP] {user_id} already assigned {role_name}")
#                 continue
 
#             body = {"principal": {"id": user_id, "type": "User"}, "role": role_name}
#             res = requests.post(
#                 f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments",
#                 headers=get_headers(),
#                 json=body
#             )
#             res.raise_for_status()
#             print(f"[ADD] Assigned {role_name} to {user_id}")
 

def main():
    print("\n=== Microsoft Fabric Deployment ===")
    
    # Step 1: Get token
    print("\n--- Get Fabric Access Token ---")
    get_access_token()
    
    # Step 2: Verify Service Principal access
    print("\n--- Verifying Authentication ---")
    if not verify_service_principal_access():
        print("[FATAL] Service Principal cannot access Fabric API")
        return
    
    # Step 3: Create/verify workspace
    print("\n--- Workspace Setup ---")    
    get_or_create_workspace()
    
    # Step 4: Assign roles
    print("\n--- Assigning Roles ---")
    # assign_roles(roles)
    get_workspace_users()
    
    
    user_id = get_user_object_id("nazmulhasan.munna@datacrafters.io")
    print(user_id)
    
     
if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"Deployment failed: {ex}")
        sys.exit(1)