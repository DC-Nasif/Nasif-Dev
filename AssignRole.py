import requests
from azure.identity import InteractiveBrowserCredential
from azure.identity import DeviceCodeCredential
from azure.identity import ClientSecretCredential

# ============== CONFIGURATION ==============

# WORKSPACE_ID = "6404d31d-7060-4956-9f8a-c7e2b65de6ac"
# USER_EMAIL = "nasif.azam@datacrafters.io"
WORKSPACE_ID = "2a88d69f-ece7-4f0a-ba33-7d76cb468b36"
# USER_EMAIL = "datacraft@canlak.com"
USER_EMAIL = "data.crafters@canlak.com"
ROLE = "Contributor"  # Options: Admin, Member, Contributor, Viewer

# ============== AUTHENTICATION ==============

# Get token for both Graph API and Fabric API
# credential = InteractiveBrowserCredential()
# credential = DeviceCodeCredential(client_id="c8bbc001-4cfc-4041-897d-949857474f4f", tenant_id="ca3f056e-4448-425a-92a9-e9d3291ea2f3")
credential = ClientSecretCredential(
    # tenant_id="ca3f056e-4448-425a-92a9-e9d3291ea2f3",
    # client_id="c8bbc001-4cfc-4041-897d-949857474f4f",
    # client_secret="rVZ8Q~XmrhsEUgX6vC6iZmf.tVsesxp_6sNOkaSW"
    tenant_id="125bc287-bece-49ea-93f8-c7fb31c7ddda",
    client_id="40bedb2f-3d98-4666-9933-09f2a2d45c55",
    client_secret="yGo8Q~zgsLxS9zwGQjd9~OBvKAB~LWKDGunPfbgu"
)

# Token for Microsoft Graph (to lookup user)
graph_token = credential.get_token("https://graph.microsoft.com/.default").token

# Token for Fabric API
fabric_token = credential.get_token("https://api.fabric.microsoft.com/.default").token

# ============== STEP 1: GET USER OBJECT ID FROM EMAIL ==============

print(f"Looking up Object ID for {USER_EMAIL}")

graph_url = f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}"

graph_headers = {"Authorization": f"Bearer {graph_token}"}

user_response = requests.get(graph_url, headers=graph_headers)

if user_response.status_code != 200:
    print(f"Failed to find user: {user_response.status_code}")
    print(user_response.text)
    exit()

user_object_id = user_response.json().get("id")

display_name = user_response.json().get("displayName")

print(f"Found: {display_name} ({user_object_id})")

# ============== STEP 2: ADD USER TO WORKSPACE ==============

print(f"Adding user to workspace as {ROLE}...")

fabric_url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/roleAssignments"
fabric_headers = {
    "Authorization": f"Bearer {fabric_token}",
    "Content-Type": "application/json"
}

payload = {
    "principal": {
        "id": user_object_id,
        "type": "User"
    },
    "role": ROLE
}

response = requests.post(fabric_url, headers=fabric_headers, json=payload)

if response.status_code == 201:
    print(f"Successfully added {USER_EMAIL} as {ROLE}")
elif response.status_code == 409:
    print(f"User already exists in workspace")
else:
    print(f"Failed: {response.status_code}")
    print(response.text)
