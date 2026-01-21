# Fabric Deployment Script

A Python-based deployment automation tool that deploys Fabric items from a Dev workspace to a Prod workspace using the Fabric REST APIs and Service Principal authentication.

## Features

✓ **Fabric Token Management** - Secure authentication using Service Principal credentials with token caching
✓ **Workspace Automation** - Automatic creation of Prod workspace if it doesn't exist
✓ **Role Assignment** - Assign roles to users/service principals in workspaces
✓ **Item Deployment** - Copy Fabric items (Reports, Semantic Models, Dataflows, etc.) from Dev to Prod
✓ **Error Handling** - Comprehensive error handling and logging
✓ **Deployment Summary** - Detailed report of deployed, failed, and skipped items

## Prerequisites

- Python 3.7 or higher
- An Azure Tenant with Fabric capacity
- A Service Principal with appropriate permissions in your Fabric tenant
- Fabric capacity provisioned and available

## Service Principal Setup

### 1. Create a Service Principal in Azure AD

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations** → **New registration**
3. Fill in the Name (e.g., "Fabric-Deployment-SP")
4. Click **Register**

### 2. Create a Client Secret

1. In your app registration, go to **Certificates & secrets**
2. Click **New client secret**
3. Add a description and expiration period
4. Copy the **Value** (this is your `CLIENT_SECRET_ENV`)

### 3. Grant Admin Permissions

1. Navigate to **API permissions**
2. Click **Add a permission**
3. Search for "Fabric" or "Power BI Service"
4. Add the following permissions:
   - `Workspace.ReadWrite.All`
   - `Item.ReadWrite.All`
5. Click **Grant admin consent**

### 4. Get Required IDs

- **Tenant ID**: Found in Azure AD → Properties → Directory ID
- **Client ID**: Found in your app registration → Overview → Application (client) ID
- **Capacity ID**: Found in your Fabric workspace settings

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Nasif-Azam/Nasif-Dev.git
cd Nasif-Dev
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file from the template:

```bash
cp config.env .env
```

4. Update `.env` with your credentials:

```
TENANT_ID_ENV=your-azure-tenant-id
CLIENT_ID_ENV=your-service-principal-client-id
CLIENT_SECRET_ENV=your-service-principal-secret
CAPACITY_ID_ENV=your-fabric-capacity-id
DEV_WORKSPACE_NAME=Dev
PROD_WORKSPACE_NAME=Prod
```

## Usage

### Basic Deployment

Run the deployment script:

```bash
python script.py
```

This will:

1. Authenticate with Fabric using your Service Principal
2. Verify or create the Prod workspace
3. Assign Admin role to the Service Principal
4. Deploy all items from Dev workspace to Prod workspace
5. Display a summary of the deployment

### Advanced Usage

You can modify `script.py` to customize the deployment:

#### Deploy only specific item types:

```python
# In the main() function, modify the deploy_items call:
deployment_summary = manager.deploy_items(
    source_workspace_id=dev_workspace_id,
    target_workspace_id=prod_workspace_id,
    item_types=["Report", "SemanticModel"]  # Only deploy reports and models
)
```

#### Assign different roles:

```python
manager.assign_role_to_user(
    workspace_id=prod_workspace_id,
    user_principal="user@domain.com",
    role="Member"  # Options: Admin, Member, Contributor, Viewer
)
```

#### Get workspace items:

```python
items = manager.get_workspace_items(workspace_id)
for item in items:
    print(f"{item['displayName']} - {item['type']}")
```

## Configuration

### Environment Variables

| Variable              | Description                    | Example                                |
| --------------------- | ------------------------------ | -------------------------------------- |
| `TENANT_ID_ENV`       | Azure Tenant ID                | `12345678-1234-1234-1234-123456789012` |
| `CLIENT_ID_ENV`       | Service Principal Client ID    | `87654321-4321-4321-4321-210987654321` |
| `CLIENT_SECRET_ENV`   | Service Principal Secret       | `abc123xyz...`                         |
| `CAPACITY_ID_ENV`     | Fabric Capacity ID             | `capacity-guid`                        |
| `DEV_WORKSPACE_NAME`  | Dev workspace name (optional)  | `Dev`                                  |
| `PROD_WORKSPACE_NAME` | Prod workspace name (optional) | `Prod`                                 |

## API Endpoints Used

- **Authentication**: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
- **Workspaces**: `https://api.fabric.microsoft.com/v1/workspaces`
- **Items**: `https://api.fabric.microsoft.com/v1/workspaces/{id}/items`
- **Role Assignments**: `https://api.fabric.microsoft.com/v1/workspaces/{id}/roleAssignments`

## Troubleshooting

### Authentication Errors

**Error**: `401 Unauthorized`

- Verify your Service Principal credentials in `.env`
- Ensure the Service Principal has admin consent for Fabric APIs
- Check that your client secret hasn't expired

### Workspace Not Found

**Error**: `Dev workspace 'Dev' not found`

- Ensure you're logged into the correct tenant
- Check the workspace name spelling
- Verify the Service Principal has access to the workspace

### Permission Denied on Items

**Error**: `403 Forbidden` when copying items

- The Service Principal needs Admin role in both Dev and Prod workspaces
- Ensure the Service Principal is added to the Dev workspace first
- Check that your Fabric capacity is active and available

### Token Expiry Issues

The script automatically handles token caching and renewal. If you see token errors:

- Check your network connectivity
- Verify tenant ID is correct
- Ensure the Service Principal secret is valid

## Logging

The script provides detailed logging output with timestamps and operation status:

- ✓ Successful operations (green)
- ✗ Failed operations (red)
- → In-progress operations
- ⊘ Skipped operations

Check the console output for real-time deployment status.

## File Structure

```
Nasif-Dev/
├── script.py                 # Main deployment script
├── requirements.txt          # Python dependencies
├── .env.example             # Configuration template
├── README.md                # This file
└── Development/             # Your Fabric items
    ├── Lakehouse.Lakehouse/
    ├── Music Sales Report.SemanticModel/
    └── Music Sales Report.Report/
```

## Best Practices

1. **Test First**: Run a test deployment to a test workspace before Prod
2. **Backup**: Ensure you have backups of your Prod workspace before deployment
3. **Scheduling**: Use task scheduler or cron jobs for automated deployments
4. **Secret Management**: Use Azure Key Vault for production deployments
5. **Monitoring**: Log deployment results for audit trails

## Deployment Workflow Example

```
1. Dev Workspace (Source)
   ├── Lakehouse
   ├── Semantic Model
   └── Reports

   ↓ (Copy via script)

2. Prod Workspace (Target)
   ├── Lakehouse_Prod
   ├── Semantic Model_Prod
   └── Reports_Prod
```

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review logs for error messages
3. Verify all prerequisites are met
4. Check Fabric API documentation

## License

See LICENSE file for details.

## Security Notes

⚠️ **Important**: Never commit `.env` files with credentials to version control. Always use `config.env` as a template and add `.env` to `.gitignore`.

For production deployments, consider:

- Using Azure Key Vault to store secrets
- Implementing audit logging
- Using managed identities where possible
- Restricting Service Principal permissions to minimum required scope
