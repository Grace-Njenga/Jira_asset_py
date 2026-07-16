import requests
import os
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================
JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EMAIL = os.getenv("Jira_Eml")
JIRA_API_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")
OBJECT_TYPE_ID = os.getenv("JIRA_OBJECT_TYPE_ID", "669")

SEARCH_TERM = "CRECIATCO0350TV"
AUTH = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json", "X-ExperimentalApi": "opt-in"}

# Asset Tag attribute ID
ASSET_TAG_ATTR_ID = 3338


def search_asset_by_asset_tag(asset_tag):
    """Search for an asset by scanning the objects in the target object type."""
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    payload = {"qlQuery": f"objectTypeId = {OBJECT_TYPE_ID}"}

    response = requests.post(url, json=payload, auth=AUTH, headers=HEADERS, timeout=20)
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code} - {response.text[:200]}")
        return []

    data = response.json()
    entries = data.get("values", []) if isinstance(data, dict) and "values" in data else data.get("objectEntries", [])

    matches = []
    for obj in entries:
        label = str(obj.get("label", ""))
        if asset_tag.lower() in label.lower():
            matches.append(obj)
            continue

        for attr in obj.get("attributes", []):
            values = attr.get("objectAttributeValues", [])
            for value_obj in values:
                value = str(value_obj.get("value", "") or value_obj.get("displayValue", "") or "")
                if asset_tag.lower() in value.lower():
                    matches.append(obj)
                    break
            if matches and matches[-1].get("id") == obj.get("id"):
                break

    return matches

def main():
    print("=" * 60)
    print(f"🔍 Searching for asset by Asset Tag: {SEARCH_TERM}")
    print(f"   Using Attribute ID: {ASSET_TAG_ATTR_ID}")
    print("=" * 60)

    results = search_asset_by_asset_tag(SEARCH_TERM)

    if results:
        print(f"✅ Found {len(results)} asset(s):")
        for obj in results:
            print(f"   Object ID: {obj['id']}")
            print(f"   Object Type ID: {obj.get('objectTypeId')}")
            print(f"   Label: {obj.get('label')}")
            
            # Show all attributes for debugging
            print(f"   Attributes:")
            for attr in obj.get('attributes', []):
                attr_id = attr.get('objectTypeAttributeId')
                values = attr.get('objectAttributeValues', [])
                if values:
                    value = values[0].get('value', '')
                    print(f"      {attr_id}: {value}")
    else:
        print("❌ No assets found.")

if __name__ == "__main__":
    main()