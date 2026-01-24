import requests
from azure.identity import ClientSecretCredential

# ============== CONFIGURATION ==============

WORKSPACE_ID = "2a88d69f-ece7-4f0a-ba33-7d76cb468b36"

# 🔹 Use Object ID directly
USER_OBJECT_ID = "c282f65e-a23c-4011-8069-1861d6528c8c"

ROLE = "Contributor"  # Admin | Member | Contributor | Viewer

# ============== AUTHENTICATION ==============

credential = ClientSecretCredential(
    tenant_id="125bc287-bece-49ea-93f8-c7fb31c7ddda",
    client_id="40bedb2f-3d98-4666-9933-09f2a2d45c55",
    client_secret="yGo8Q~zgsLxS9zwGQjd9~OBvKAB~LWKDGunPfbgu"
)

# Token for Fabric API
fabric_token = credential.get_token(
    "https://api.fabric.microsoft.com/.default"
).token

# ============== ASSIGN ROLE ==============

print(f"Assigning role '{ROLE}' to Object ID: {USER_OBJECT_ID}")

fabric_url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/roleAssignments"

headers = {
    "Authorization": f"Bearer {fabric_token}",
    "Content-Type": "application/json"
}

payload = {
    "principal": {
        "id": USER_OBJECT_ID,
        "type": "User"
    },
    "role": ROLE
}

response = requests.post(fabric_url, headers=headers, json=payload)

if response.status_code == 201:
    print(f"Successfully assigned {ROLE}")
elif response.status_code == 409:
    print("ℹUser already has a role in this workspace")
else:
    print(f"Failed: {response.status_code}")
    print(response.text)
