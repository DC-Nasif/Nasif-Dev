import os
import json
import requests
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential
import time
import shutil
import subprocess
import base64

# Load environment variables
load_dotenv()

# Global variables
tenant_id = os.getenv('TENANT_ID')
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
capacity_id = os.getenv('CAPACITY_ID')
dev_workspace_id = os.getenv('DEV_WORKSPACE_ID')
prod_workspace_id = os.getenv('PROD_WORKSPACE_ID')
prod_workspace_name = os.getenv('PROD_WORKSPACE_NAME')
skip_role_assignment = os.getenv('SKIP_ROLE_ASSIGNMENT', 'false').lower() == 'true'

fabric_api_url = "https://api.fabric.microsoft.com/v1"
access_token = None

# Step 1: Generate access token
def get_access_token():
    """Generate access token using Service Principal credentials"""
    try:
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
        token = credential.get_token("https://api.fabric.microsoft.com/.default")
        global access_token
        access_token = token.token
        print("[OK] Access token generated successfully")
        return access_token
    except Exception as e:
        print(f"[ERROR] Error generating access token: {e}")
        raise

# Step 2: Get authorization headers
def get_headers():
    """Return authorization headers"""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

# Step 3: Create a workspace if it doesn't exist
def create_workspace(workspace_name, workspace_id=None):
    """Create workspace if it doesn't exist"""
    try:
        if workspace_id:
            url = f"{fabric_api_url}/workspaces/{workspace_id}"
            response = requests.get(url, headers=get_headers())
            
            if response.status_code == 200:
                print(f"[OK] Workspace '{workspace_name}' exists")
                return response.json()
        
        payload = {
            "displayName": workspace_name,
            "capacityId": capacity_id
        }
        response = requests.post(
            f"{fabric_api_url}/workspaces",
            headers=get_headers(),
            json=payload
        )
        
        if response.status_code in [200, 201]:
            workspace = response.json()
            print(f"[OK] Workspace created successfully")
            print(f"Workspace: {workspace}")
            print(f"Workspace Name: {workspace_name}")
            return workspace
        elif response.status_code == 409:
            print(f"[OK] Workspace already exists (409)")
            return {"id": workspace_id} if workspace_id else None
        else:
            print(f"[ERROR] Workspace creation failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] Workspace error: {e}")
        raise

# Step 4: Verify Service Principal access
def verify_service_principal_access():
    """Verify SP can access Fabric API"""
    try:
        url = f"{fabric_api_url}/workspaces"
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

# Step 5: Get role assignments in the workspace
def get_role_assignments(workspace_id):
    """Get existing roles to avoid duplicates"""
    try:
        url = f"{fabric_api_url}/workspaces/{workspace_id}/roleAssignments"
        response = requests.get(url, headers=get_headers())
        
        if response.status_code == 403:
            print(f"[WARNING] Cannot list roles (403). Service Principal may not be assigned yet.")
            return []
            
        response.raise_for_status()
        return response.json().get("value", [])
    except Exception as e:
        print(f"[WARNING] Failed to get role assignments: {e}")
        return []

# Step 6: Assign a role to a workspace
def assign_role_to_workspace(workspace_id, principal_id, 
                              principal_type="ServicePrincipal", role="Admin"):
    """Assign a role to a workspace if necessary"""
    if skip_role_assignment:
        print(f"[SKIP] Role assignment disabled in config")
        return True
    
    print(f"[INFO] Attempting role assignment...")
    existing_roles = get_role_assignments(workspace_id)
    
    # Check if already assigned
    for ra in existing_roles:
        if ra.get("principal", {}).get("id") == principal_id:
            current_role = ra.get("role")
            if current_role in ["Admin", role]:
                print(f"[OK] Principal already has {current_role} role")
                return True
    
    # Try to assign
    try:
        url = f"{fabric_api_url}/workspaces/{workspace_id}/roleAssignments"
        payload = {
            "principal": {"id": principal_id, "type": principal_type},
            "role": role
        }
        
        response = requests.post(url, headers=get_headers(), json=payload)
        
        if response.status_code in [200, 201]:
            print(f"[OK] Assigned {role} role successfully")
            return True
        elif response.status_code == 403:
            print(f"[WARNING] Cannot auto-assign role (403 Forbidden)")
            print(f"[ACTION REQUIRED] Please manually assign {role} role to this principal in Fabric workspace settings:")
            print(f"  Principal ID: {principal_id}")
            print(f"[INFO] Continuing deployment...")
            return True  # Continue anyway
        else:
            print(f"[ERROR] Role assignment failed: {response.status_code}")
            print(f"[ERROR] {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Role assignment error: {e}")
        return False

# Step 7: Get items from GitHub repository
def get_items_from_github(repo_url="https://github.com/Nasif-Azam/Nasif-Dev", 
                          branch="Dev-Branch"):
    """Clone and retrieve items"""
    try:
        if os.path.exists("temp_fabric_repo"):
            shutil.rmtree("temp_fabric_repo", ignore_errors=True)
        
        print(f"[INFO] Cloning repository...")
        subprocess.run(["git", "clone", "--branch", branch, repo_url, "temp_fabric_repo"], 
                      check=True, capture_output=True)
        
        dev_path = os.path.join("temp_fabric_repo", "Development")
        items = []
        
        if not os.path.exists(dev_path):
            print("[ERROR] Development folder not found")
            return []
        
        for item_name in os.listdir(dev_path):
            item_path = os.path.join(dev_path, item_name)
            if os.path.isdir(item_path):
                itype = "Unknown"
                if ".Report" in item_name: itype = "Report"
                elif ".SemanticModel" in item_name: itype = "SemanticModel"
                elif ".Lakehouse" in item_name: itype = "Lakehouse"
                elif ".Notebook" in item_name: itype = "Notebook"
                elif ".Dataflow" in item_name: itype = "Dataflow"
                
                if itype != "Unknown":
                    items.append({
                        "displayName": item_name.split('.')[0],
                        "type": itype,
                        "path": item_path
                    })
        
        print(f"[OK] Found {len(items)} items to deploy")
        return items
    except Exception as e:
        print(f"[ERROR] Git clone failed: {e}")
        return []

# Step 8: Copy item to workspace
def copy_item_to_workspace(item, target_workspace_id):
    """Deploy item to workspace with Base64 encoding"""
    try:
        item_type = item.get('type')
        item_name = item.get('displayName')
        item_path = item.get('path')
        
        def_map = {
            'Report': 'definition.pbir',
            'SemanticModel': 'definition.pbism',
            'Lakehouse': 'lakehouse.metadata.json',
            'Dataflow': 'mashup.pq',
            'Notebook': 'notebook-content.py'
        }
        
        logical_file = def_map.get(item_type)
        if not logical_file:
            print(f"[SKIP] Unknown definition for {item_type}")
            return False
        
        file_path = os.path.join(item_path, logical_file)
        
        if item_type == 'Notebook' and not os.path.exists(file_path):
            file_path = os.path.join(item_path, f"{item_name}.ipynb")
            logical_file = f"{item_name}.ipynb"
        
        if not os.path.exists(file_path):
            print(f"[WARNING] File not found: {file_path}")
            return False
        
        # Read and Base64 encode
        with open(file_path, 'rb') as f:
            raw_content = f.read()
            base64_content = base64.b64encode(raw_content).decode('utf-8')
        
        # Create payload
        payload = {
            "displayName": item_name,
            "type": item_type,
            "definition": {
                "parts": [
                    {
                        "path": logical_file,
                        "payload": base64_content,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        }
        
        url = f"{fabric_api_url}/workspaces/{target_workspace_id}/items"
        response = requests.post(url, headers=get_headers(), json=payload)
        
        if response.status_code in [200, 201, 202]:
            print(f"[OK] Created {item_name}")
            return True
        else:
            print(f"[ERROR] Failed to create {item_name}: {response.status_code}")
            if response.status_code == 401:
                print(f"[ACTION] Service Principal needs workspace permissions (assign role manually)")
            print(f"[DEBUG] {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

# Main function to orchestrate all steps
def main():
    print("\n=== Microsoft Fabric Deployment ===\n")
    
    # Step 1: Get token
    get_access_token()
    
    # Step 2: Verify SP access
    print("--- Verifying Authentication ---")
    if not verify_service_principal_access():
        print("[FATAL] Service Principal cannot access Fabric API")
        return
    
    # Step 3: Create/verify workspace
    print("\n--- Workspace Setup ---")
    ws = create_workspace(prod_workspace_name, prod_workspace_id)
    if not ws:
        print("[FATAL] Cannot proceed without workspace")
        return
    ws_id = ws.get('id', prod_workspace_id)
    
    # Step 4: Assign roles
    print("\n--- Role Assignment ---")
    assign_role_to_workspace(ws_id, client_id, principal_type="ServicePrincipal")
    
    # Step 5: Get items
    print("\n--- Fetching Items ---")
    items = get_items_from_github()
    if not items:
        print("[FATAL] No items to deploy")
        return
    
    # Step 6: Deploy items
    print("\n--- Deploying Items ---")
    success_count = 0
    for item in items:
        if copy_item_to_workspace(item, ws_id):
            success_count += 1
        time.sleep(2)
    
    # Step 7: Cleanup
    if os.path.exists("temp_fabric_repo"):
        shutil.rmtree("temp_fabric_repo", ignore_errors=True)
    
    print(f"\n=== Deployment Complete ===")
    print(f"Successfully deployed: {success_count}/{len(items)} items\n")

# Run the main function
if __name__ == "__main__":
    main()
