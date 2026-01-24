import os
import sys
import json
# import yaml
import requests
import time
# import pyodbc
from azure.identity import InteractiveBrowserCredential
from azure.identity import DeviceCodeCredential
from azure.identity import ClientSecretCredential
 
 
# ---------------- CONFIG LOADING ----------------
# def load_config(path="config.yml"):
#     with open(path, "r", encoding="utf-8") as f:
#         return yaml.safe_load(f)["config"]
 
# def load_user_input(path="config.json"):
#     with open(path, "r", encoding="utf-8") as f:
#         return json.load(f)
 
 
 # Azure Tenant ID
tenant_id="125bc287-bece-49ea-93f8-c7fb31c7ddda"

# Service Principal Client ID (Application ID)
client_id="40bedb2f-3d98-4666-9933-09f2a2d45c55"

# Service Principal Client Secret
client_secret="yGo8Q~zgsLxS9zwGQjd9~OBvKAB~LWKDGunPfbgu"

# Fabric Capacity ID
# capacity_id="59AB60EE-4E92-4A22-A8E0-0B31B00314CD"

workspace_name = "test"

roles = [
    {
        "role_name": "Contributor",
        "users": [
            "c282f65e-a23c-4011-8069-1861d6528c8c"
        ]
    }
    # {
    #     "role_name": "Member",
    #     "users": [
    #         "user-object-id-3"
    #     ]
    # }
]




# ============== CONFIGURATION ==============

# WORKSPACE_ID = "6404d31d-7060-4956-9f8a-c7e2b65de6ac"
# USER_EMAIL = "nasif.azam@datacrafters.io"
# WORKSPACE_ID = "2a88d69f-ece7-4f0a-ba33-7d76cb468b36"
# # USER_EMAIL = "datacraft@canlak.com"
# USER_EMAIL = "data.crafters@canlak.com"
# ROLE = "Contributor"  # Options: Admin, Member, Contributor, Viewer

FABRIC_API = "https://api.fabric.microsoft.com/v1"

# ============== AUTHENTICATION ==============

# Get token for both Graph API and Fabric API
# credential = InteractiveBrowserCredential()
# credential = DeviceCodeCredential(client_id="c8bbc001-4cfc-4041-897d-949857474f4f", tenant_id="ca3f056e-4448-425a-92a9-e9d3291ea2f3")
# credential = ClientSecretCredential(
#     # tenant_id="ca3f056e-4448-425a-92a9-e9d3291ea2f3",
#     # client_id="c8bbc001-4cfc-4041-897d-949857474f4f",
#     # client_secret="rVZ8Q~XmrhsEUgX6vC6iZmf.tVsesxp_6sNOkaSW"
#     tenant_id="125bc287-bece-49ea-93f8-c7fb31c7ddda",
#     client_id="40bedb2f-3d98-4666-9933-09f2a2d45c55",
#     client_secret="yGo8Q~zgsLxS9zwGQjd9~OBvKAB~LWKDGunPfbgu"
# )

def get_access_token(tenant_id, client_id, client_secret):
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    body = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://api.fabric.microsoft.com/.default"
    }
    res = requests.post(url, data=body)
    res.raise_for_status()
    return res.json()["access_token"]

# ---------------- WORKSPACE ----------------
def get_workspace_id(token, workspace_name):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{FABRIC_API}/workspaces", headers=headers)
    res.raise_for_status()
 
    for ws in res.json().get("value", []):
        if ws["displayName"].lower() == workspace_name.lower():
            print(f"Workspace exists: {workspace_name} ({ws['id']})")
            return ws["id"]
 
    print(f"Workspace does not exist: {workspace_name}")
    return None

def get_role_assignments(token, workspace_id):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments", headers=headers)
    res.raise_for_status()
    return res.json().get("value", [])
 
def assign_roles(token, workspace_id, roles):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    existing = {(ra["principal"]["id"], ra["role"]) for ra in get_role_assignments(token, workspace_id)}
 
    for role in roles:
        role_name = role["role_name"]
        for user_id in role.get("users", []):
            if (user_id, role_name) in existing:
                print(f"[SKIP] {user_id} already assigned {role_name}")
                continue
 
            body = {"principal": {"id": user_id, "type": "User"}, "role": role_name}
            res = requests.post(
                f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments",
                headers=headers,
                json=body
            )
            res.raise_for_status()
            print(f"[ADD] Assigned {role_name} to {user_id}")
            
            
def main():
    # tenant_id, client_id, client_secret
    token = get_access_token(tenant_id, client_id, client_secret)
    workspace_id = get_workspace_id(token, workspace_name)
    assign_roles(token, workspace_id, roles)
    # Deploy
    
     
if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"❌ Deployment failed: {ex}")
        sys.exit(1)