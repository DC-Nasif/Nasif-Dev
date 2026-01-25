import os
import requests
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv
import shutil
import subprocess
import json
import base64
from git import Repo
from fabric_cicd import (
    FabricWorkspace,
    publish_all_items,
    unpublish_all_orphan_items
)

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CAPACITY_ID = os.getenv("CAPACITY_ID")
WORKSPACE_NAME = os.getenv("WORKSPACE_NAME")

FABRIC_API = "https://api.fabric.microsoft.com/v1"

GITHUB_REPO = "https://github.com/DC-Nasif/Nasif-Dev.git"
GITHUB_BRANCH = "Dev-Branch"
CLONE_DIR = "repo_clone"
REPO_NAME = "Nasif-Dev"

CLONE_DIR = "repo_clone"

TARGET_ENVIRONMENT = "Nasif-Prod"

access_token = None
workspace_id = None

ITEM_TYPES_IN_SCOPE = [
    "Lakehouse",
    "Dataflow",
    "Report",
    "SemanticModel"
]

# roles = [
#     {
#         "role_name": "Admin",
#         "users": [
#             "c8bbc001-4cfc-4041-897d-949857474f4f",
#             "nasif.azam@datacrafters.io"
#         ]
#     }
# ]

# user_email = "nazmulhasan.munna@datacrafters.io"
user_email = "nasif.azam@datacrafters.io"
user_role = "Contributor"

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
    # 1️) Check existing workspaces
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

    # 2️) Create workspace if not found
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
    users = response.json().get("value", [])
    existing_users_email = set()

    for u in users:
        u_email = u.get("emailAddress")
        user_id = u.get("identifier")
        role = u.get("groupUserAccessRight")
        principal_type = u.get("principalType")
        if u_email:
            existing_users_email.add(u_email)

        print(f"** UserID: {user_id}, Email: {u_email}, Role: {role}, PrincipalType: {principal_type}")

    return existing_users_email


def get_token(scope):
    try:
        credential = ClientSecretCredential(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        )
        token = credential.get_token(scope).token
        print(f"[OK] Token generated for scope: {scope}")
        print("Secondary token:", token)
        return token
    except Exception as e:
        print(f"[ERROR] Token generation failed: {e}")
        raise


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


def get_user_object_id():
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}"
    user_response = requests.get(url, headers=get_graph_headers())
    
    if user_response.status_code != 200:
        print(f"Failed to find user: {user_response.status_code}")
        print(user_response.text)
        # exit()
        return None
    else:
        print("User Object ID:", user_response.json()["id"])
        user_response.raise_for_status()
        return user_response.json()["id"]


def get_role_assignments():
    get_role_response = requests.get(
        f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments", 
        headers=get_headers()
        )
    get_role_response.raise_for_status()
    current_roles = get_role_response.json().get("value", [])
    return current_roles
 
 
def assign_roles():
    # existing_workspace_users = get_workspace_users()
    # existing_role_assignments = {
    #     (ra["principal"]["id"], ra["role"])
    #     for ra in get_role_assignments()
    # }

    # user_id = "65d56aef-261f-4a9e-b295-26cd16cea64a"
    user_id = get_user_object_id()
    role_name = user_role

    body = {
        "principal": {
            "id": user_id,
            "type": "App"
        },
        "role": role_name
    }
    print("BODY",body)
    res = requests.post(
        f"{FABRIC_API}/workspaces/{workspace_id}/roleAssignments",
        headers=get_headers(),
        json=body
    )
    res.raise_for_status()
    print(f"[ADD] Assigned {role_name} to {user_id}")


# # ---------------- GITHUB ---------------- #
# def clone_repo():
#     if os.path.exists(CLONE_DIR):
#         shutil.rmtree(CLONE_DIR)

#     subprocess.run(
#         ["git", "clone", "-b", GITHUB_BRANCH, GITHUB_REPO, CLONE_DIR],
#         check=True
#     )
#     print("[OK] GitHub repo cloned")


# def print_repo_tree(base_path):
#     print("\nCloned Repository Structure:\n")

#     for root, dirs, files in os.walk(base_path):
#         level = root.replace(base_path, "").count(os.sep)
#         indent = " " * 4 * level
#         print(f"{indent} {os.path.basename(root)}/")

#         subindent = " " * 4 * (level + 1)
#         for f in files:
#             if f.endswith(".json"):
#                 print(f"{subindent} {f}")


# # ---------------- DEPLOY ITEMS ---------------- #
# def deploy_item(token, workspace_id, item_type, item_path):
#     with open(item_path, "r", encoding="utf-8") as f:
#         payload = json.load(f)

#     url = f"{FABRIC_API}/workspaces/{workspace_id}/{item_type}"
#     res = requests.post(url, headers=get_headers(token), json=payload)

#     if res.status_code in [200, 201]:
#         print(f"[DEPLOYED] {item_type} -> {os.path.basename(item_path)}")
#     else:
#         print(f"[FAILED] {item_type}")
#         print(res.text)


# def deploy_all_items():
#     base = os.path.join(CLONE_DIR, "Development")

#     mappings = {
#         "lakehouses": "Lakehouse",
#         "warehouses": "Warehouse",
#         "semanticModels": "SemanticModel",
#         "reports": "Report"
#     }

#     for api_endpoint, folder in mappings.items():
#         folder_path = os.path.join(base, folder)
#         if not os.path.exists(folder_path):
#             continue

#         for file in os.listdir(folder_path):
#             if file.endswith(".json"):
#                 deploy_item(
#                     access_token,
#                     workspace_id,
#                     api_endpoint,
#                     os.path.join(folder_path, file)
#                 )



# -----------------------------
# CLONE REPO (if not exists)
# -----------------------------
def clone_repo():
    if not os.path.exists(CLONE_DIR):
        Repo.clone_from(GITHUB_REPO, CLONE_DIR)
        print("[OK] Repo cloned")
    else:
        print("[INFO] Repo already exists")

# -----------------------------
# FIND DEVELOPMENT FOLDER
# -----------------------------
def get_development_path():
    # dev_path = os.path.join(CLONE_DIR, REPO_NAME, "Development")
    dev_path = os.path.join(CLONE_DIR, REPO_NAME)
    if not os.path.exists(dev_path):
        raise FileNotFoundError(f"Development folder not found at {dev_path}")
    else:
        print(f"[INFO] Development folder found at: {dev_path}")
    return dev_path

# -----------------------------
# DEPLOY
# -----------------------------
def deploy():
    repository_directory = get_development_path()

    print(f"[INFO] Deploying from: {repository_directory}")
    print(f"[INFO] Target workspace: {workspace_id}")

    target_workspace = FabricWorkspace(
        workspace_id=workspace_id,
        environment=TARGET_ENVIRONMENT,
        repository_directory=repository_directory,
        item_type_in_scope=ITEM_TYPES_IN_SCOPE
    )

    # Publish items
    publish_all_items(target_workspace)
    print("[OK] Items published successfully")

    # Remove orphan items
    unpublish_all_orphan_items(target_workspace)
    print("[OK] Orphan items unpublished")



def main():
    print("\n########## Microsoft Fabric Deployment ##########")
    
    # Step 1: Get token
    print("\n========== Get Fabric Access Token ==========")
    get_access_token()
    
    # Step 2: Verify Service Principal access
    print("\n========== Verifying Authentication ==========")
    if not verify_service_principal_access():
        print("[FATAL] Service Principal cannot access Fabric API")
        return
    
    # Step 3: Create/verify workspace
    print("\n========== Workspace Setup ==========")    
    get_or_create_workspace()
    
    # Step 4: Get existing workspace users
    print("\n========== Existing Workspace Users ==========")
    existing_users_email = get_workspace_users()
    print(f"Existing users email: {existing_users_email}")
    print(f"User email: {user_email}")
    
    # Step 5: Assign roles
    print("\n========== Assigning Roles ==========")
    if user_email in existing_users_email:
        print(f"{user_email} user already exists in workspace. So skipping role assignment.")
        print("See Current Roles Assignments Details: \n", get_role_assignments())        
    else:
        print(f"{user_email} user does not exist in workspace.")
        print(f"Assigning Roles to {user_email}")
        assign_roles()
        print("See Current Roles Assignments Details: \n", get_role_assignments())        
     

    print("\n========== Deploying All Items ==========")
    print(f"[INFO] Deploying to workspace: {workspace_id}")
    # deploy_items()
    clone_repo()
    deploy()
    

    #  # Step 6: Clone GitHub repo
    # print("\n========== Cloning GitHub Repo ==========")
    # clone_repo()     
    
    # # NEW: Print repo contents
    # # print_repo_tree(os.path.join(CLONE_DIR, "Development"))
    
    # # Step 7: Deploy all items
    # print("\n========== Deploying All Items ==========")
    # deploy_all_items()
     
if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"Deployment failed: {ex}")
        # sys.exit(1)