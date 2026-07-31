import os
import sys
import re
import requests
from dotenv import load_dotenv

load_dotenv()

ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID")
ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID")
ENTRA_CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET")
ENTRA_GROUP_IDS = [x.strip() for x in (os.getenv("ENTRA_GROUP_IDS") or "").split(",") if x.strip()]
REQUEST_TIMEOUT = 30
GUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def fail(message):
    print(f"[ERROR] {message}")
    sys.exit(1)


def info(message):
    print(f"[INFO] {message}")


def warn(message):
    print(f"[WARN] {message}")


def is_guid(value):
    return bool(value and GUID_PATTERN.match(value))


def permission_hint(response_text):
    if "Authorization_RequestDenied" in response_text or "Insufficient privileges" in response_text:
        return (
            "App permissions are not enough for this call. In Entra, add Microsoft Graph application permissions such as "
            "User.Read.All and Group.Read.All, then grant admin consent."
        )
    return ""


def validate_config():
    missing = []
    for key, value in {
        "ENTRA_TENANT_ID": ENTRA_TENANT_ID,
        "ENTRA_CLIENT_ID": ENTRA_CLIENT_ID,
        "ENTRA_CLIENT_SECRET": ENTRA_CLIENT_SECRET,
    }.items():
        if not value:
            missing.append(key)

    if missing:
        fail(f"Missing required .env values: {', '.join(missing)}")


def get_graph_token():
    token_url = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/oauth2/v2.0/token"
    payload = {
        "client_id": ENTRA_CLIENT_ID,
        "client_secret": ENTRA_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    response = requests.post(token_url, data=payload, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        fail(f"Token request failed: {response.status_code} {response.text[:300]}")

    token = response.json().get("access_token")
    if not token:
        fail("Token response missing access_token")

    return token


def graph_get(url, token, params=None):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    return response


def test_tenant(token):
    info("Testing tenant access via /organization...")
    url = "https://graph.microsoft.com/v1.0/organization?$select=id,displayName,verifiedDomains"
    response = graph_get(url, token)
    if response.status_code != 200:
        warn(f"Tenant test failed: {response.status_code} {response.text[:300]}")
        hint = permission_hint(response.text)
        if hint:
            warn(hint)
        return False

    data = response.json()
    values = data.get("value", [])
    if not values:
        warn("Tenant test succeeded, but no organization records were returned.")
        return True

    org = values[0]
    info(f"Connected tenant: {org.get('displayName') or org.get('id')}")
    return True


def test_users(token):
    info("Testing user read access via /users?$top=1...")
    url = "https://graph.microsoft.com/v1.0/users?$top=1&$select=id,displayName,userPrincipalName,mail,accountEnabled"
    response = graph_get(url, token)
    if response.status_code != 200:
        warn(f"User test failed: {response.status_code} {response.text[:300]}")
        hint = permission_hint(response.text)
        if hint:
            warn(hint)
        return False

    data = response.json()
    users = data.get("value", [])
    if not users:
        warn("User test succeeded, but no users were returned.")
        return True

    user = users[0]
    info(
        "Sample user: "
        f"{user.get('displayName') or ''} | "
        f"{user.get('userPrincipalName') or user.get('mail') or ''} | "
        f"Enabled={user.get('accountEnabled')}"
    )
    return True


def test_groups(token):
    if not ENTRA_GROUP_IDS:
        warn("No ENTRA_GROUP_IDS configured, skipping group tests.")
        return True

    ok = True
    for group_id in ENTRA_GROUP_IDS:
        if not is_guid(group_id):
            warn(f"Skipping placeholder group id: {group_id}. Replace it with a real Entra group Object ID.")
            continue

        info(f"Testing group access for {group_id}...")
        url = f"https://graph.microsoft.com/v1.0/groups/{group_id}?$select=id,displayName,mail"
        response = graph_get(url, token)
        if response.status_code != 200:
            warn(f"Group test failed for {group_id}: {response.status_code} {response.text[:300]}")
            hint = permission_hint(response.text)
            if hint:
                warn(hint)
            ok = False
            continue

        group = response.json()
        info(f"Group OK: {group.get('displayName') or group.get('id')}")

    return ok


def main():
    validate_config()
    print("[*] Starting Entra ID connection test...")
    print("[INFO] Required Graph app permissions for a full test: User.Read.All, Group.Read.All, Directory.Read.All or equivalent admin-consented application permissions.")

    token = get_graph_token()
    print("[OK] Graph token acquired")

    results = [
        test_tenant(token),
        test_users(token),
        test_groups(token),
    ]

    print("\n==================================================")
    print("ENTRA ID CONNECTION TEST COMPLETE")
    print("==================================================")
    print(f"Overall status: {'PASS' if all(results) else 'FAIL'}")
    print("==================================================")


if __name__ == "__main__":
    main()
