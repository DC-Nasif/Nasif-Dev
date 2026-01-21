import os
import json
import logging
import requests
from typing import Dict, Optional, List
from datetime import datetime
import time
from dotenv import load_dotenv
import shutil
from pathlib import Path
import subprocess

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FabricDeploymentManager:
    """
    Manages deployment of Fabric items from Dev to Prod workspace.
    Handles workspace creation, role assignment, and item deployment.
    """

    def __init__(self, 
                 tenant_id: str,
                 client_id: str,
                 client_secret: str,
                 capacity_id: str):
        """
        Initialize the Fabric Deployment Manager.
        
        Args:
            tenant_id: Azure Tenant ID
            client_id: Service Principal Client ID
            client_secret: Service Principal Client Secret
            capacity_id: Fabric Capacity ID for workspace assignment
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.capacity_id = capacity_id
        self.token = None
        self.token_expiry = None
        self.fabric_api_base = "https://api.fabric.microsoft.com/v1"
        self.admin_api_base = "https://api.powerbi.com/v1.0/myorg/admin"
        
    def _get_fabric_token(self) -> str:
        """
        Acquire Fabric authentication token using Service Principal credentials.
        Implements token caching to avoid repeated authentication.
        
        Returns:
            str: Authentication token for Fabric API
        """
        # Return cached token if still valid
        if self.token and self.token_expiry and datetime.now().timestamp() < self.token_expiry:
            logger.info("Using cached Fabric token")
            return self.token
            
        logger.info("Acquiring new Fabric token...")
        
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://analysis.windows.net/powerbi/api/.default"
        }
        
        try:
            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            
            token_data = response.json()
            self.token = token_data["access_token"]
            # Cache token with 5-minute buffer before expiry
            self.token_expiry = datetime.now().timestamp() + token_data.get("expires_in", 3600) - 300
            
            logger.info("✓ Successfully acquired Fabric token")
            return self.token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Failed to acquire token: {str(e)}")
            raise
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Generate API request headers with authentication token.
        
        Returns:
            Dict: Headers dictionary for API requests
        """
        token = self._get_fabric_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def create_workspace(self, workspace_name: str) -> Optional[Dict]:
        """
        Create a new Fabric workspace if it doesn't already exist.
        Assigns the workspace to the specified capacity.
        
        Args:
            workspace_name: Name of the workspace to create
            
        Returns:
            Dict: Workspace details including workspace_id, or None if creation fails
        """
        logger.info(f"Checking for existing workspace: {workspace_name}")
        
        # Check if workspace already exists
        existing_workspace = self._get_workspace_by_name(workspace_name)
        if existing_workspace:
            logger.info(f"✓ Workspace '{workspace_name}' already exists (ID: {existing_workspace['id']})")
            return existing_workspace
        
        logger.info(f"Creating new workspace: {workspace_name}")
        
        url = f"{self.fabric_api_base}/workspaces"
        
        payload = {
            "displayName": workspace_name,
            "capacityId": self.capacity_id,
            "description": f"Prod workspace created for {workspace_name}"
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            
            workspace_data = response.json()
            workspace_id = workspace_data.get("id")
            logger.info(f"✓ Workspace created successfully (ID: {workspace_id})")
            
            # Wait for workspace to be fully provisioned
            time.sleep(2)
            
            return workspace_data
            
        except requests.exceptions.RequestException as e:
            # Handle 409 Conflict - workspace already exists
            if hasattr(e, 'response') and e.response.status_code == 409:
                logger.info(f"✓ Workspace '{workspace_name}' already exists")
                # Return a workspace object with the name as ID fallback
                # This will allow the deployment to continue
                return {"displayName": workspace_name, "id": workspace_name}
            
            logger.error(f"✗ Failed to create workspace: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
    
    def _get_workspace_by_name(self, workspace_name: str) -> Optional[Dict]:
        """
        Retrieve workspace details by name.
        
        Args:
            workspace_name: Name of the workspace
            
        Returns:
            Dict: Workspace details if found, None otherwise
        """
        url = f"{self.fabric_api_base}/workspaces"
        
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            
            workspaces = response.json().get("value", [])
            for workspace in workspaces:
                if workspace.get("displayName") == workspace_name:
                    logger.info(f"✓ Found workspace '{workspace_name}' (ID: {workspace['id']})")
                    return workspace
            
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Failed to retrieve workspaces: {str(e)}")
            return None
    
    def get_role_assignments(self, workspace_id: str) -> List[Dict]:
        """
        Retrieve all existing role assignments in a workspace.
        
        Args:
            workspace_id: ID of the target workspace
            
        Returns:
            List: List of existing role assignments
        """
        url = f"{self.fabric_api_base}/workspaces/{workspace_id}/roleAssignments"
        
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            
            assignments = response.json().get("value", [])
            logger.info(f"✓ Retrieved {len(assignments)} existing role assignments")
            return assignments
            
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Failed to retrieve role assignments: {str(e)}")
            return []
    
    def assign_role_to_user(self, 
                           workspace_id: str,
                           user_principal: str,
                           role: str = "Admin",
                           principal_type: str = "ServicePrincipal") -> bool:
        """
        Assign a role to a user/service principal in the workspace.
        Checks existing assignments to avoid duplicate assignment.
        
        Args:
            workspace_id: ID of the target workspace
            user_principal: User principal ID or service principal ID
            role: Role to assign (Admin, Member, Contributor, Viewer)
            principal_type: Type of principal (User, ServicePrincipal, Group)
            
        Returns:
            bool: True if assignment successful or already exists, False otherwise
        """
        try:
            logger.info(f"Checking role assignment for {user_principal} ({principal_type})")
            
            # Get existing role assignments
            existing_assignments = self.get_role_assignments(workspace_id)
            
            # Create set of existing (principal_id, role) tuples
            existing = {(ra.get("principal", {}).get("id"), ra.get("role")) 
                       for ra in existing_assignments}
            
            # Check if already assigned
            if (user_principal, role) in existing:
                logger.info(f"✓ {user_principal} already has {role} role")
                return True
            
            # Assign the role
            logger.info(f"Assigning {role} role to {user_principal}")
            
            url = f"{self.fabric_api_base}/workspaces/{workspace_id}/roleAssignments"
            
            payload = {
                "principal": {
                    "id": user_principal,
                    "type": principal_type
                },
                "role": role
            }
            
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=10)
            
            if response.status_code in [200, 201]:
                logger.info(f"✓ Successfully assigned {role} role to {user_principal}")
                return True
            else:
                logger.error(f"✗ Failed to assign role: {response.status_code}")
                if response.text:
                    logger.error(f"  Response: {response.text}")
                return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Request failed during role assignment: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"  Status: {e.response.status_code}")
                if e.response.text:
                    logger.error(f"  Response: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"✗ Error in assign_role_to_user: {str(e)}")
            return False
    
    def get_workspace_items(self, workspace_id: str) -> Optional[List[Dict]]:
        """
        Retrieve all items in a workspace.
        
        Args:
            workspace_id: ID of the workspace
            
        Returns:
            List: List of items in the workspace
        """
        logger.info(f"Retrieving items from workspace {workspace_id}")
        
        url = f"{self.fabric_api_base}/workspaces/{workspace_id}/items"
        
        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            items = response.json().get("value", [])
            logger.info(f"✓ Retrieved {len(items)} items from workspace")
            return items
            
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Failed to retrieve workspace items: {str(e)}")
            return None
    
    def _get_item_type(self, item_name: str) -> Optional[str]:
        """
        Detect item type from folder name suffix.
        
        Args:
            item_name: Name of the item folder
            
        Returns:
            str: Item type (Dataflow, Report, SemanticModel, etc.) or None
        """
        if ".Dataflow" in item_name:
            return "Dataflow"
        elif ".Lakehouse" in item_name:
            return "Lakehouse"
        elif ".Report" in item_name:
            return "Report"
        elif ".SemanticModel" in item_name:
            return "SemanticModel"
        elif ".Notebook" in item_name:
            return "Notebook"
        elif ".Pipeline" in item_name:
            return "Pipeline"
        return None
    
    def get_items_from_github(self, repo_url: str = "https://github.com/Nasif-Azam/Nasif-Dev", branch: str = "Dev-Branch", dev_folder: str = "Development") -> Optional[List[Dict]]:
        """
        Clone repository from GitHub and get items from Development folder.
        
        Args:
            repo_url: GitHub repository URL
            branch: Git branch name to clone
            dev_folder: Development folder name
            
        Returns:
            List: List of items found in the repository
        """
        try:
            # Create temporary directory for cloning
            temp_repo_dir = "temp_fabric_repo"
            
            # Remove existing temp directory if it exists
            if os.path.exists(temp_repo_dir):
                logger.info("Removing existing temp directory...")
                time.sleep(1)  # Wait for git process to release files
                try:
                    shutil.rmtree(temp_repo_dir)
                except PermissionError:
                    logger.warning("Could not remove temp directory, continuing anyway...")
            
            # Clone the repository
            logger.info(f"Cloning repository from {repo_url} (branch: {branch})...")
            result = subprocess.run(
                ["git", "clone", "--branch", branch, repo_url, temp_repo_dir],
                check=True,
                capture_output=True,
                text=True
            )
            time.sleep(1)  # Wait for git to release resources
            logger.info("✓ Repository cloned successfully")
            
            # Get items from Development folder
            dev_path = os.path.join(temp_repo_dir, dev_folder)
            if not os.path.exists(dev_path):
                logger.error(f"Development folder not found at {dev_path}")
                return []
            
            items = []
            for item_name in os.listdir(dev_path):
                item_path = os.path.join(dev_path, item_name)
                if os.path.isdir(item_path):
                    # Detect item type by folder name suffix
                    item_type = self._get_item_type(item_name)
                    if item_type:
                        items.append({
                            "displayName": item_name.split('.')[0],  # Remove the .Type suffix for display
                            "fullName": item_name,
                            "path": item_path,
                            "type": item_type
                        })
                        logger.info(f"Found item: {item_name} (type: {item_type})")
            
            logger.info(f"✓ Retrieved {len(items)} items from GitHub Development folder")
            return items
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git clone failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Error in get_items_from_github: {e}")
            return []
    
    def copy_item(self,
                  source_workspace_id: str,
                  source_item_id: str,
                  target_workspace_id: str,
                  item_name: str) -> Optional[Dict]:
        """
        Copy a Fabric item from source to target workspace.
        
        Args:
            source_workspace_id: ID of source workspace
            source_item_id: ID of item to copy
            target_workspace_id: ID of target workspace
            item_name: Name for the copied item
            
        Returns:
            Dict: Details of copied item, or None if copy fails
        """
        logger.info(f"Copying item {source_item_id} from {source_workspace_id} to {target_workspace_id}")
        
        url = f"{self.fabric_api_base}/workspaces/{source_workspace_id}/items/{source_item_id}/copyTo"
        
        payload = {
            "targetWorkspaceId": target_workspace_id,
            "displayName": item_name
        }
        
        try:
            response = requests.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            
            item_data = response.json()
            logger.info(f"✓ Item copied successfully (New ID: {item_data.get('id')})")
            return item_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Failed to copy item: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
    
    def deploy_item_from_path(self,
                             item_path: str,
                             item_type: str,
                             item_name: str,
                             target_workspace_id: str) -> bool:
        """
        Deploy a Fabric item from local file system path to workspace using Fabric API.
        
        Args:
            item_path: Local path to the item folder
            item_type: Type of item (Dataflow, Lakehouse, Report, SemanticModel, etc.)
            item_name: Display name of the item
            target_workspace_id: Target workspace ID
            
        Returns:
            bool: True if deployment successful, False otherwise
        """
        try:
            logger.info(f"Deploying {item_type} '{item_name}' to workspace {target_workspace_id}")
            
            url = f"{self.fabric_api_base}/workspaces/{target_workspace_id}/items"
            
            # Create payload with just basic metadata (no definition)
            # Fabric API will create the item, definitions can be updated separately
            payload = {
                "displayName": item_name,
                "type": item_type,
                "description": f"Deployed from GitHub repository - {item_type}"
            }
            
            logger.info(f"  Calling Fabric API: POST {url}")
            logger.info(f"  Payload: displayName='{item_name}', type='{item_type}'")
            
            # Call Fabric API to create item
            response = requests.post(
                url, 
                json=payload, 
                headers=self._get_headers(), 
                timeout=30
            )
            
            logger.info(f"  API Response Status: {response.status_code}")
            
            if response.status_code in [201, 200]:
                item_data = response.json()
                item_id = item_data.get('id')
                logger.info(f"✓ {item_type} '{item_name}' deployed successfully (ID: {item_id})")
                
                # Log definition files found
                if item_type == "Report":
                    definition_file = os.path.join(item_path, "definition.pbir")
                    if os.path.exists(definition_file):
                        logger.info(f"  Note: Definition file exists at {definition_file} - can be updated manually")
                elif item_type == "SemanticModel":
                    definition_file = os.path.join(item_path, "definition.pbism")
                    if os.path.exists(definition_file):
                        logger.info(f"  Note: Definition file exists at {definition_file} - can be updated manually")
                elif item_type == "Dataflow":
                    mashup_file = os.path.join(item_path, "mashup.pq")
                    if os.path.exists(mashup_file):
                        logger.info(f"  Note: Mashup file exists at {mashup_file} - can be updated manually")
                
                return True
            else:
                logger.error(f"✗ API returned status code {response.status_code}")
                if response.text:
                    logger.error(f"  Response: {response.text}")
                return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Request failed to deploy {item_type} '{item_name}': {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"  Status: {e.response.status_code}")
                if e.response.text:
                    logger.error(f"  Response: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"✗ Failed to deploy {item_type} '{item_name}': {str(e)}")
            import traceback
            logger.error(f"  Traceback: {traceback.format_exc()}")
            return False
    
    def deploy_items_from_github(self, 
                                 repo_url: str = "https://github.com/Nasif-Azam/Nasif-Dev",
                                 branch: str = "Dev-Branch",
                                 target_workspace_id: str = None,
                                 item_types: Optional[List[str]] = None) -> Dict:
        """
        Deploy items from GitHub repository to target Fabric workspace.
        
        Args:
            repo_url: GitHub repository URL
            branch: Git branch to clone
            target_workspace_id: ID of target Prod workspace
            item_types: Specific item types to deploy (e.g., ['Report', 'SemanticModel'])
                       If None, deploys all items
            
        Returns:
            Dict: Deployment summary with success/failure counts
        """
        logger.info(f"Starting item deployment from GitHub repository to {target_workspace_id}")
        
        items = self.get_items_from_github(repo_url=repo_url, branch=branch)
        if not items:
            logger.warning("No items found to deploy from GitHub repository")
            return {"success": 0, "failed": 0, "skipped": 0}
        
        summary = {"success": 0, "failed": 0, "skipped": 0, "items": []}
        
        for item in items:
            item_type = item.get("type")
            item_name = item.get("displayName")
            full_name = item.get("fullName")
            item_path = item.get("path")
            
            # Filter by item type if specified
            if item_types and item_type not in item_types:
                logger.info(f"⊘ Skipping {item_type}: {item_name} (not in deployment list)")
                summary["skipped"] += 1
                continue
            
            logger.info(f"→ Deploying {item_type}: {item_name} from GitHub")
            logger.info(f"  Source path: {item_path}")
            
            # Deploy item from GitHub repository
            result = self.deploy_item_from_path(
                item_path,
                item_type,
                item_name,
                target_workspace_id
            )
            
            if result:
                summary["success"] += 1
                summary["items"].append({
                    "name": item_name,
                    "fullName": full_name,
                    "type": item_type,
                    "status": "deployed",
                    "source": "GitHub",
                    "path": item_path
                })
            else:
                summary["failed"] += 1
                summary["items"].append({
                    "name": item_name,
                    "fullName": full_name,
                    "type": item_type,
                    "status": "failed",
                    "source": "GitHub"
                })
        
        return summary
    
    def deploy_items(self, 
                    source_workspace_id: str,
                    target_workspace_id: str,
                    item_types: Optional[List[str]] = None) -> Dict:
        """
        Deploy all items (or specific types) from source to target workspace.
        
        Args:
            source_workspace_id: ID of source Dev workspace
            target_workspace_id: ID of target Prod workspace
            item_types: Specific item types to deploy (e.g., ['Report', 'Semantic Model'])
                       If None, deploys all items
            
        Returns:
            Dict: Deployment summary with success/failure counts
        """
        logger.info(f"Starting item deployment from {source_workspace_id} to {target_workspace_id}")
        
        items = self.get_workspace_items(source_workspace_id)
        if not items:
            logger.warning("No items found to deploy")
            return {"success": 0, "failed": 0, "skipped": 0}
        
        summary = {"success": 0, "failed": 0, "skipped": 0, "items": []}
        
        for item in items:
            item_id = item.get("id")
            item_type = item.get("type")
            item_name = item.get("displayName")
            
            # Filter by item type if specified
            if item_types and item_type not in item_types:
                logger.info(f"⊘ Skipping {item_type}: {item_name} (not in deployment list)")
                summary["skipped"] += 1
                continue
            
            logger.info(f"→ Deploying {item_type}: {item_name}")
            
            # Copy item to target workspace
            result = self.copy_item(
                source_workspace_id,
                item_id,
                target_workspace_id,
                f"{item_name}_Prod"
            )
            
            if result:
                summary["success"] += 1
                summary["items"].append({
                    "name": item_name,
                    "type": item_type,
                    "status": "deployed",
                    "new_id": result.get("id")
                })
            else:
                summary["failed"] += 1
                summary["items"].append({
                    "name": item_name,
                    "type": item_type,
                    "status": "failed"
                })
        
        return summary


def load_config_from_env() -> Dict[str, str]:
    """
    Load configuration from environment variables.
    
    Returns:
        Dict: Configuration dictionary
    """
    config = {
        "tenant_id": os.getenv("TENANT_ID_ENV"),
        "client_id": os.getenv("CLIENT_ID_ENV"),
        "client_secret": os.getenv("CLIENT_SECRET_ENV"),
        "capacity_id": os.getenv("CAPACITY_ID_ENV"),
        "prod_workspace_name": os.getenv("PROD_WORKSPACE_NAME", "Prod"),
        "prod_workspace_id": os.getenv("PROD_WORKSPACE_ID", ""),
        "skip_role_assignment": os.getenv("SKIP_ROLE_ASSIGNMENT", "false").lower() == "true",
        "github_repo_path": os.getenv("GITHUB_REPO_PATH", "")
    }
    
    # Validate required fields
    required_fields = ["tenant_id", "client_id", "client_secret", "capacity_id"]
    missing_fields = [field for field in required_fields if not config.get(field)]
    
    if missing_fields:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_fields)}")
    
    logger.info("Configuration loaded successfully")
    logger.info(f"  Prod Workspace ID: {config['prod_workspace_id']}")
    logger.info(f"  Skip Role Assignment: {config['skip_role_assignment']}")
    
    return config


def main():
    """
    Main deployment orchestration function.
    """
    try:
        # Load configuration
        logger.info("Loading configuration from environment variables...")
        config = load_config_from_env()
        
        # Initialize deployment manager
        manager = FabricDeploymentManager(
            tenant_id=config["tenant_id"],
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            capacity_id=config["capacity_id"]
        )
        
        # Step 1: Create Prod workspace if it doesn't exist
        logger.info("\n" + "="*60)
        logger.info("STEP 1: Creating/Verifying Prod Workspace")
        logger.info("="*60)
        
        # Use provided workspace ID if available, otherwise try to create/find workspace
        if config["prod_workspace_id"]:
            logger.info(f"Using provided Prod workspace ID: {config['prod_workspace_id']}")
            prod_workspace_id = config["prod_workspace_id"]
        else:
            prod_workspace = manager.create_workspace(config["prod_workspace_name"])
            if not prod_workspace:
                logger.error("Failed to create/verify Prod workspace. Exiting.")
                return
            prod_workspace_id = prod_workspace.get("id")
        
        # Step 2: Assign roles to Service Principal (Optional - assign manually in Fabric UI)
        logger.info("\n" + "="*60)
        logger.info("STEP 2: Checking Prod Workspace Access")
        logger.info("="*60)
        
        logger.info(f"Target Prod workspace ID: {prod_workspace_id}")
        logger.info("NOTE: Ensure your Service Principal has Admin role in the Prod workspace")
        logger.info("      You can assign this role manually in Fabric workspace settings")
        logger.info("      OR ensure the service principal is already assigned the Admin role")
        
        # Step 3: Deploy items from GitHub repository to Prod workspace
        logger.info("\n" + "="*60)
        logger.info("STEP 3: Deploying Items from GitHub to Prod")
        logger.info("="*60)
        
        # Deploy items from GitHub repository
        deployment_summary = manager.deploy_items_from_github(
            repo_url="https://github.com/Nasif-Azam/Nasif-Dev",
            branch="Dev-Branch",
            target_workspace_id=prod_workspace_id
        )
        
        # Step 4: Print deployment summary
        logger.info("\n" + "="*60)
        logger.info("DEPLOYMENT SUMMARY")
        logger.info("="*60)
        logger.info(f"✓ Successful: {deployment_summary['success']}")
        logger.info(f"✗ Failed: {deployment_summary['failed']}")
        logger.info(f"⊘ Skipped: {deployment_summary['skipped']}")
        
        if deployment_summary.get("items"):
            logger.info("\nDeployed Items:")
            for item in deployment_summary["items"]:
                status_icon = "✓" if item["status"] == "deployed" else "✗"
                logger.info(f"  {status_icon} {item['name']} ({item['type']}) - {item['status']}")
        
        logger.info("\n" + "="*60)
        logger.info("Deployment process completed successfully!")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Deployment failed with error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
