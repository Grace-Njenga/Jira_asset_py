import csv
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# CONFIGURATION (.env)
# =========================================================
# Jira
JIRA_URL = os.getenv("Jira_url", "").rstrip("/")
JIRA_EMAIL = os.getenv("Jira_Eml")
JIRA_API_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")

# Entra ID / Azure AD (client credentials)
ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID")
ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID")
ENTRA_CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET")
ENTRA_GROUP_IDS = [x.strip() for x in (os.getenv("ENTRA_GROUP_IDS") or "").split(",") if x.strip()]

# Migration target (Jira Assets)
JIRA_USER_OBJECT_TYPE_ID = os.getenv("JIRA_USER_OBJECT_TYPE_ID")
JIRA_USER_MATCH_ATTRIBUTE = os.getenv("JIRA_USER_MATCH_ATTRIBUTE", "Email")

# Optional map from internal record keys to Jira attribute names.
# Example:
# JIRA_USER_ATTR_NAME_MAP_JSON={"pn":"PN","email":"Email","department":"Department"}
DEFAULT_ATTR_NAME_MAP = {
    "pn": "PN",
    "email": "Email",
    "department": "Department",
    "mailrecipient_info": "mailrecipient.info",
    "mailnickname": "mailnickname",
    "manager_display_name": "Manager Display Name",
    "manager_email": "Manager Email",
    "is_active": "Is Active",
    "is_enabled": "Is Enabled",
    "created_at": "Created At",
    "updated_at": "Updated At",
    "location": "Location",
    "country": "Country",
}

JIRA_USER_ATTR_NAME_MAP_JSON = os.getenv("JIRA_USER_ATTR_NAME_MAP_JSON", "")

# Export outputs for audit
CSV_EXPORT_FILENAME = "ad_user_data_export.csv"
JSON_EXPORT_FILENAME = "ad_user_data_export.json"

REQUEST_TIMEOUT = 40


# =========================================================
# HELPERS
# =========================================================
def fail(message):
    print(f"[ERROR] {message}")
    sys.exit(1)


def info(message):
    print(f"[INFO] {message}")


def warn(message):
    print(f"[WARN] {message}")


def escape_aql_literal(value):
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')


def jira_headers():
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-ExperimentalApi": "opt-in",
    }


def jira_auth():
    return (JIRA_EMAIL, JIRA_API_TOKEN)


def parse_attr_name_map():
    if not JIRA_USER_ATTR_NAME_MAP_JSON.strip():
        return DEFAULT_ATTR_NAME_MAP.copy()

    try:
        parsed = json.loads(JIRA_USER_ATTR_NAME_MAP_JSON)
        if not isinstance(parsed, dict):
            warn("JIRA_USER_ATTR_NAME_MAP_JSON is not a JSON object. Falling back to defaults.")
            return DEFAULT_ATTR_NAME_MAP.copy()

        merged = DEFAULT_ATTR_NAME_MAP.copy()
        for key, value in parsed.items():
            if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
                merged[key.strip()] = value.strip()
        return merged
    except json.JSONDecodeError:
        warn("JIRA_USER_ATTR_NAME_MAP_JSON invalid JSON. Falling back to defaults.")
        return DEFAULT_ATTR_NAME_MAP.copy()


def validate_config():
    missing = []
    for key, value in {
        "Jira_url": JIRA_URL,
        "Jira_Eml": JIRA_EMAIL,
        "Jira_Token": JIRA_API_TOKEN,
        "Wkspace_ID": WORKSPACE_ID,
        "ENTRA_TENANT_ID": ENTRA_TENANT_ID,
        "ENTRA_CLIENT_ID": ENTRA_CLIENT_ID,
        "ENTRA_CLIENT_SECRET": ENTRA_CLIENT_SECRET,
        "JIRA_USER_OBJECT_TYPE_ID": JIRA_USER_OBJECT_TYPE_ID,
    }.items():
        if not value:
            missing.append(key)

    if missing:
        fail(f"Missing required .env values: {', '.join(missing)}")

    if not ENTRA_GROUP_IDS:
        fail("Missing ENTRA_GROUP_IDS in .env. Provide comma-separated Entra group IDs.")


# =========================================================
# ENTRA ID (MICROSOFT GRAPH)
# =========================================================
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
        fail(f"Failed to obtain Graph token: {response.status_code} {response.text[:300]}")

    token = response.json().get("access_token")
    if not token:
        fail("Graph token response missing access_token")

    return token


def get_entra_group_users(token, group_id):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = (
        f"https://graph.microsoft.com/v1.0/groups/{group_id}/members"
        f"?$select=id,displayName,userPrincipalName,mail,accountEnabled&$top=999"
    )

    users = []
    while url:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            warn(f"Failed to read group {group_id}: {response.status_code} {response.text[:240]}")
            break

        data = response.json()
        values = data.get("value", [])
        for item in values:
            if item.get("@odata.type") != "#microsoft.graph.user":
                continue

            email = (item.get("mail") or item.get("userPrincipalName") or "").strip().lower()
            if not email:
                continue

            users.append(
                {
                    "email": email,
                    "display_name": item.get("displayName") or email,
                    "active": bool(item.get("accountEnabled", False)),
                    "entra_id": item.get("id"),
                    "group_id": group_id,
                }
            )

        url = data.get("@odata.nextLink")

    return users


def collect_entra_users(token):
    users_by_email = {}

    for group_id in ENTRA_GROUP_IDS:
        group_users = get_entra_group_users(token, group_id)
        info(f"Fetched {len(group_users)} users from Entra group {group_id}")

        for user in group_users:
            email = user["email"]
            existing = users_by_email.get(email)
            if existing is None:
                users_by_email[email] = user
            else:
                existing["active"] = existing["active"] or user["active"]

    return users_by_email


def get_entra_user_profile(token, user_id):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    select_fields = [
        "id",
        "displayName",
        "userPrincipalName",
        "mail",
        "employeeId",
        "department",
        "mailNickname",
        "officeLocation",
        "country",
        "accountEnabled",
        "createdDateTime",
        "lastPasswordChangeDateTime",
        "onPremisesExtensionAttributes",
    ]
    select_query = ",".join(select_fields)
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}?$select={select_query}"

    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        warn(f"Failed profile fetch for user {user_id}: {response.status_code} {response.text[:180]}")
        return None

    return response.json()


def get_entra_user_manager(token, user_id):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/manager?$select=displayName,mail,userPrincipalName"

    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    if response.status_code == 200:
        data = response.json()
        manager_email = data.get("mail") or data.get("userPrincipalName")
        return {
            "manager_display_name": data.get("displayName") or "",
            "manager_email": (manager_email or "").strip().lower(),
        }

    if response.status_code != 404:
        warn(f"Failed manager fetch for user {user_id}: {response.status_code} {response.text[:180]}")

    return {"manager_display_name": "", "manager_email": ""}


def build_user_data_record(group_user, profile, manager):
    # "PN" is mapped to employeeId.
    pn_value = profile.get("employeeId") or ""

    # "mailrecipient.info" mapped from extensionAttribute1 by default.
    ext_attrs = profile.get("onPremisesExtensionAttributes") or {}
    mailrecipient_info = ext_attrs.get("extensionAttribute1") or ""

    email_value = (profile.get("mail") or profile.get("userPrincipalName") or group_user.get("email") or "").strip().lower()
    is_enabled = bool(profile.get("accountEnabled", False))

    return {
        "pn": pn_value,
        "email": email_value,
        "department": profile.get("department") or "",
        "mailrecipient_info": mailrecipient_info,
        "mailnickname": profile.get("mailNickname") or "",
        "manager_display_name": manager.get("manager_display_name") or "",
        "manager_email": manager.get("manager_email") or "",
        "is_active": is_enabled,
        "is_enabled": is_enabled,
        "created_at": profile.get("createdDateTime") or "",
        # Microsoft Graph has no generic updatedDateTime for user; using password change timestamp.
        "updated_at": profile.get("lastPasswordChangeDateTime") or "",
        "location": profile.get("officeLocation") or "",
        "country": profile.get("country") or "",
    }


# =========================================================
# JIRA ASSETS MIGRATION (UPSERT)
# =========================================================
def get_jira_attribute_id_map(object_type_id):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttype/{object_type_id}/attributes"
    response = requests.get(url, headers=jira_headers(), auth=jira_auth(), timeout=REQUEST_TIMEOUT)

    if response.status_code != 200:
        fail(f"Failed to fetch Jira object type attributes: {response.status_code} {response.text[:300]}")

    data = response.json()
    attrs = data if isinstance(data, list) else data.get("values", [])

    name_to_id = {}
    for attr in attrs:
        name = attr.get("name")
        attr_id = attr.get("id")
        if name and attr_id is not None:
            name_to_id[name.strip().lower()] = attr_id

    return name_to_id


def find_jira_object_by_match_attr(object_type_id, match_attr_name, match_value):
    if match_value in [None, ""]:
        return None

    escaped = escape_aql_literal(str(match_value).strip())
    escaped_attr = escape_aql_literal(match_attr_name.strip())
    query = f'objectTypeId = {object_type_id} AND "{escaped_attr}" = "{escaped}"'

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    payload = {"qlQuery": query}
    response = requests.post(url, json=payload, headers=jira_headers(), auth=jira_auth(), timeout=REQUEST_TIMEOUT)

    if response.status_code != 200:
        warn(f"AQL lookup failed for {match_attr_name}={match_value}: {response.status_code} {response.text[:200]}")
        return None

    data = response.json()
    entries = data.get("values", []) if isinstance(data, dict) and "values" in data else data.get("objectEntries", [])
    if not isinstance(entries, list) or not entries:
        return None

    return entries[0].get("id")


def build_jira_assets_payload(record, attr_name_map, jira_attr_id_map):
    attributes = []

    for record_key, jira_attr_name in attr_name_map.items():
        value = record.get(record_key)
        if value in [None, ""]:
            continue

        attr_id = jira_attr_id_map.get(jira_attr_name.strip().lower())
        if attr_id is None:
            continue

        attributes.append(
            {
                "objectTypeAttributeId": attr_id,
                "objectAttributeValues": [{"value": value}],
            }
        )

    return attributes


def create_jira_object(object_type_id, attributes):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/create"
    payload = {
        "objectTypeId": int(object_type_id),
        "attributes": attributes,
    }
    response = requests.post(url, json=payload, headers=jira_headers(), auth=jira_auth(), timeout=REQUEST_TIMEOUT)

    if response.status_code not in (200, 201):
        return False, response.text[:300]

    return True, "created"


def update_jira_object(object_id, attributes):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/{object_id}"
    payload = {"attributes": attributes}
    response = requests.put(url, json=payload, headers=jira_headers(), auth=jira_auth(), timeout=REQUEST_TIMEOUT)

    if response.status_code != 200:
        return False, response.text[:300]

    return True, "updated"


def migrate_records_to_jira_assets(records, object_type_id, attr_name_map):
    jira_attr_id_map = get_jira_attribute_id_map(object_type_id)

    match_attr_name = JIRA_USER_MATCH_ATTRIBUTE.strip()
    if match_attr_name.lower() not in jira_attr_id_map:
        fail(
            f'Match attribute "{match_attr_name}" not found in Jira object type {object_type_id}. '
            "Update JIRA_USER_MATCH_ATTRIBUTE or object attributes."
        )

    summary = {
        "created": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
    }

    for record in records:
        match_key = None
        for key, attr_name in attr_name_map.items():
            if attr_name.strip().lower() == match_attr_name.lower():
                match_key = key
                break

        if match_key is None:
            fail(
                f'No record-key mapping found for match attribute "{match_attr_name}". '
                "Add it in JIRA_USER_ATTR_NAME_MAP_JSON."
            )

        match_value = record.get(match_key)
        if not match_value:
            summary["skipped"] += 1
            continue

        attributes = build_jira_assets_payload(record, attr_name_map, jira_attr_id_map)
        if not attributes:
            summary["skipped"] += 1
            continue

        object_id = find_jira_object_by_match_attr(object_type_id, match_attr_name, match_value)
        if object_id:
            ok, message = update_jira_object(object_id, attributes)
            if ok:
                summary["updated"] += 1
            else:
                summary["failed"] += 1
                warn(f"Update failed for {match_attr_name}={match_value}: {message}")
        else:
            ok, message = create_jira_object(object_type_id, attributes)
            if ok:
                summary["created"] += 1
            else:
                summary["failed"] += 1
                warn(f"Create failed for {match_attr_name}={match_value}: {message}")

    return summary


# =========================================================
# EXPORT
# =========================================================
def export_user_data(records):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, CSV_EXPORT_FILENAME)
    json_path = os.path.join(script_dir, JSON_EXPORT_FILENAME)

    fieldnames = [
        "pn",
        "email",
        "department",
        "mailrecipient_info",
        "mailnickname",
        "manager_display_name",
        "manager_email",
        "is_active",
        "is_enabled",
        "created_at",
        "updated_at",
        "location",
        "country",
    ]

    with open(csv_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)

    with open(json_path, mode="w", encoding="utf-8") as json_file:
        json.dump(records, json_file, indent=2)

    info(f"User data CSV exported to: {csv_path}")
    info(f"User data JSON exported to: {json_path}")


# =========================================================
# MAIN
# =========================================================
def run_sync():
    validate_config()

    info("User data migration started (migration-only mode).")
    info(f"Target Jira object type: {JIRA_USER_OBJECT_TYPE_ID}")

    token = get_graph_token()
    users_by_email = collect_entra_users(token)

    records = []
    for user in sorted(users_by_email.values(), key=lambda x: x["email"]):
        user_id = user.get("entra_id")
        if not user_id:
            continue

        profile = get_entra_user_profile(token, user_id)
        if profile is None:
            continue

        manager = get_entra_user_manager(token, user_id)
        records.append(build_user_data_record(user, profile, manager))

    export_user_data(records)

    attr_name_map = parse_attr_name_map()
    migration_summary = migrate_records_to_jira_assets(records, JIRA_USER_OBJECT_TYPE_ID, attr_name_map)

    print("\n==================================================")
    print("USER DATA MIGRATION COMPLETE")
    print("==================================================")
    print(f"Users collected from Entra groups: {len(users_by_email)}")
    print(f"User records prepared:            {len(records)}")
    print(f"Jira objects created:             {migration_summary['created']}")
    print(f"Jira objects updated:             {migration_summary['updated']}")
    print(f"Jira objects skipped:             {migration_summary['skipped']}")
    print(f"Jira object migration failures:   {migration_summary['failed']}")
    print("==================================================")


if __name__ == "__main__":
    run_sync()
