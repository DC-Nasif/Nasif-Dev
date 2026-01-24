import os
import sys
import json
# import yaml
import requests
import time
# import pyodbc
 
FABRIC_API = "https://api.fabric.microsoft.com/v1"
 
# ---------------- CONFIG LOADING ----------------
# def load_config(path="config.yml"):
#     with open(path, "r", encoding="utf-8") as f:
#         return yaml.safe_load(f)["config"]
 
# def load_user_input(path="config.json"):
#     with open(path, "r", encoding="utf-8") as f:
#         return json.load(f)

 
 # Azure Tenant ID
tenant_id="ca3f056e-4448-425a-92a9-e9d3291ea2f3"

# Service Principal Client ID (Application ID)
client_id="c8bbc001-4cfc-4041-897d-949857474f4f"

# Service Principal Client Secret
client_secret="rVZ8Q~XmrhsEUgX6vC6iZmf.tVsesxp_6sNOkaSW"

# Fabric Capacity ID
capacity_id="59AB60EE-4E92-4A22-A8E0-0B31B00314CD"

workspace_name = "Nasif-Prod"

roles = [
    {
        "role_name": "Admin",
        "users": [
            "user-object-id-1",
            "user-object-id-2"
        ]
    }
    # {
    #     "role_name": "Member",
    #     "users": [
    #         "user-object-id-3"
    #     ]
    # }
]

 
 
# ---------------- SERVICE PRINCIPAL ----------------
# def resolve_sp_credentials(sp_cfg: dict):
#     def resolve(val: str) -> str:
#         return os.environ.get(val, val)
 
#     # tenant_id = resolve(sp_cfg["tenant_id_env"])
#     # client_id = resolve(sp_cfg["client_id_env"])
#     # client_secret = resolve(sp_cfg["client_secret_env"])
 
#     if not all([tenant_id, client_id, client_secret]):
#         raise Exception("Missing SP credentials")
#     return tenant_id, client_id, client_secret
 
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
    tenant_id, client_id, client_secret
    token = get_access_token(tenant_id, client_id, client_secret)
    workspace_id = get_workspace_id(token, workspace_name)
    assign_roles(token, workspace_id, roles)
    # Deploy
    
     
if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"Deployment failed: {ex}")
        sys.exit(1)