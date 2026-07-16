import requests
import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. CONFIGURATION
# ==========================================
JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EMAIL = os.getenv("Jira_Eml")
JIRA_API_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")

JIRA_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
JIRA_AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)

# Jira Attribute IDs for "Used By"
USED_BY_EMAIL_ATTR_ID = 3348
USED_BY_NAME_ATTR_ID = 3380

# The specific asset and user data we already extracted
TARGET_ASSET_NAME = "ABCIT03452L"
FS_USER_EMAIL = "t.mungubariki@cgiar.org"
FS_USER_NAME = "Tumaini Mungubariki"

# ==========================================
# 2. MAIN LOGIC
# ==========================================

def main():
    print(f"🎯 Target Asset Name: {TARGET_ASSET_NAME}")
    print(f"👤 User to assign: {FS_USER_NAME} ({FS_USER_EMAIL})\n")
    
    # Step 1: Search Jira for the asset by its Name
    print("🔍 Searching Jira for asset with Name = 'ABCIT03452L'...")
    aql_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    
    # AQL to match the built-in Name attribute
    aql = f'Name == "{TARGET_ASSET_NAME}"'
    print(f"   Executing AQL: {aql}")
    
    res = requests.post(aql_url, json={"qlQuery": aql}, headers=JIRA_HEADERS, auth=JIRA_AUTH)
    
    jira_object_id = None
    
    if res.status_code == 200:
        entries = res.json().get('objectEntries', [])
        if len(entries) > 0:
            jira_object_id = entries[0]['id']
            print(f"   ✅ SUCCESS! Found asset in Jira. Object ID: {jira_object_id}")
        else:
            print("   ⚠️ AQL returned 200 OK, but found 0 objects with that exact Name.")
            print("   💡 Trying fallback: Searching by Hostname attribute...")
            
            # Fallback: Sometimes the data is in the Hostname attribute, not the built-in Name
            aql_fallback = f'Hostname = "{TARGET_ASSET_NAME}"'
            res2 = requests.post(aql_url, json={"qlQuery": aql_fallback}, headers=JIRA_HEADERS, auth=JIRA_AUTH)
            if res2.status_code == 200:
                entries2 = res2.json().get('objectEntries', [])
                if len(entries2) > 0:
                    jira_object_id = entries2[0]['id']
                    print(f"   ✅ SUCCESS via fallback! Found asset. Object ID: {jira_object_id}")
    else:
        print(f"   ❌ AQL Search Error ({res.status_code}): {res.text[:200]}")
        return

    if not jira_object_id:
        print("\n❌ Could not find the asset in Jira to update.")
        return

    # Step 2: Update the "Used By" fields
    print(f"\n🚀 Updating 'Used By' fields for Object ID: {jira_object_id}...")
    update_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/{jira_object_id}"
    
    payload = {
        "attributes": [
            {
                "objectTypeAttributeId": USED_BY_EMAIL_ATTR_ID,
                "objectAttributeValues": [{"value": str(FS_USER_EMAIL)}]
            },
            {
                "objectTypeAttributeId": USED_BY_NAME_ATTR_ID,
                "objectAttributeValues": [{"value": str(FS_USER_NAME)}]
            }
        ]
    }
    
    update_res = requests.put(update_url, json=payload, headers=JIRA_HEADERS, auth=JIRA_AUTH)
    
    if update_res.status_code == 200:
        print("✅ SUCCESS! 'Used By' fields updated in Jira.")
        print(f"   -> Used By (Email): {FS_USER_EMAIL}")
        print(f"   -> Used By (Name):  {FS_USER_NAME}")
    else:
        print(f"❌ Failed to update Jira. Status Code: {update_res.status_code}")
        print(f"   Response: {update_res.text[:300]}")

if __name__ == "__main__":
    main()