import os
import json
import requests
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential
import time
import shutil
import subprocess
import base64

load_dotenv()

class FabricDeploymentManager:
    def __init__(self):
        self.tenant_id = os.getenv('TENANT_ID_ENV')
        self.client_id = os.getenv('CLIENT_ID_ENV')
        self.client_secret = os.getenv('CLIENT_SECRET_ENV')
        self.capacity_id = os.getenv('CAPACITY_ID_ENV')
        self.dev_workspace_id = os.getenv('DEV_WORKSPACE_ID')
        self.prod_workspace_id = os.getenv('PROD_WORKSPACE_ID')
        self.prod_workspace_name = os.getenv('PROD_WORKSPACE_NAME')
        self.skip_role_assignment = os.getenv('SKIP_ROLE_ASSIGNMENT', 'false').lower() == 'true'
        
        self.fabric_api_url = "https://api.fabric.microsoft.com/v1"
        self.access_token = None
        
    def get_access_token(self):
        """Generate access token using Service Principal credentials"""
        try:
            credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            token = credential.get_token("https://api.fabric.microsoft.com/.default")
            self.access_token = token.token
            print("[OK] Access token generated successfully")
            return self.access_token
        except Exception as e:
            print(f"[ERROR] Error generating access token: {e}")
            raise
    
    def get_headers(self):
        """Return authorization headers"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def create_workspace(self, workspace_name, workspace_id=None):
        """Create workspace if it doesn't exist"""
        try:
            if workspace_id:
                url = f"{self.fabric_api_url}/workspaces/{workspace_id}"
                response = requests.get(url, headers=self.get_headers())
                
                if response.status_code == 200:
                    print(f"[OK] Workspace '{workspace_name}' exists")
                    return response.json()
            
            payload = {
                "displayName": workspace_name,
                "capacityId": self.capacity_id
            }
            response = requests.post(
                f"{self.fabric_api_url}/workspaces",
                headers=self.get_headers(),
                json=payload
            )
            
            if response.status_code in [200, 201]:
                workspace = response.json()
                print(f"[OK] Workspace created successfully")
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
    
    def verify_service_principal_access(self):
        """Verify SP can access Fabric API"""
        try:
            url = f"{self.fabric_api_url}/workspaces"
            response = requests.get(url, headers=self.get_headers())
            
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
    
    def get_role_assignments(self, workspace_id):
        """Get existing roles to avoid duplicates"""
        try:
            url = f"{self.fabric_api_url}/workspaces/{workspace_id}/roleAssignments"
            response = requests.get(url, headers=self.get_headers())
            
            if response.status_code == 403:
                print(f"[WARNING] Cannot list roles (403). Service Principal may not be assigned yet.")
                return []
                
            response.raise_for_status()
            return response.json().get("value", [])
        except Exception as e:
            print(f"[WARNING] Failed to get role assignments: {e}")
            return []
    
    def assign_role_to_workspace(self, workspace_id, principal_id, 
                                principal_type="ServicePrincipal", role="Admin"):
        """
        If assignment fails due to insufficient privileges, continue
        (assume manual assignment was done in Azure Portal).
        """
        if self.skip_role_assignment:
            print(f"[SKIP] Role assignment disabled in config")
            return True
        
        print(f"[INFO] Attempting role assignment...")
        existing_roles = self.get_role_assignments(workspace_id)
        
        # Check if already assigned
        for ra in existing_roles:
            if ra.get("principal", {}).get("id") == principal_id:
                current_role = ra.get("role")
                if current_role in ["Admin", role]:
                    print(f"[OK] Principal already has {current_role} role")
                    return True
        
        # Try to assign
        try:
            url = f"{self.fabric_api_url}/workspaces/{workspace_id}/roleAssignments"
            payload = {
                "principal": {"id": principal_id, "type": principal_type},
                "role": role
            }
            
            response = requests.post(url, headers=self.get_headers(), json=payload)
            
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
    
    def get_items_from_github(self, repo_url="https://github.com/Nasif-Azam/Nasif-Dev", 
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
    
    def copy_item_to_workspace(self, item, target_workspace_id):
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
            
            url = f"{self.fabric_api_url}/workspaces/{target_workspace_id}/items"
            response = requests.post(url, headers=self.get_headers(), json=payload)
            
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
    
    def deploy_all_items(self):
        """Main deployment orchestration"""
        print("\n=== Microsoft Fabric Deployment ===\n")
        
        # Get token
        self.get_access_token()
        
        # Verify SP access
        print("--- Verifying Authentication ---")
        if not self.verify_service_principal_access():
            print("[FATAL] Service Principal cannot access Fabric API")
            return
        
        # Create/verify workspace
        print("\n--- Workspace Setup ---")
        ws = self.create_workspace(self.prod_workspace_name, self.prod_workspace_id)
        if not ws:
            print("[FATAL] Cannot proceed without workspace")
            return
        ws_id = ws.get('id', self.prod_workspace_id)
        
        # Assign roles
        print("\n--- Role Assignment ---")
        self.assign_role_to_workspace(ws_id, self.client_id, principal_type="ServicePrincipal")
        
        # Get items
        print("\n--- Fetching Items ---")
        items = self.get_items_from_github()
        if not items:
            print("[FATAL] No items to deploy")
            return
        
        # Deploy items
        print("\n--- Deploying Items ---")
        success_count = 0
        for item in items:
            if self.copy_item_to_workspace(item, ws_id):
                success_count += 1
            time.sleep(2)
        
        # Cleanup
        if os.path.exists("temp_fabric_repo"):
            shutil.rmtree("temp_fabric_repo", ignore_errors=True)
        
        print(f"\n=== Deployment Complete ===")
        print(f"Successfully deployed: {success_count}/{len(items)} items\n")


if __name__ == "__main__":
    manager = FabricDeploymentManager()
    manager.deploy_all_items()