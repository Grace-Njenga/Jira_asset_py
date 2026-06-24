import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# Configuration
FS_DOMAIN = "alliance.freshservice.com"
FS_API_KEY = "DbbbetkOM_FKsb-5s7c8"
FS_LAPTOP_TYPE_ID = "26000466712"
JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EML = os.getenv("Jira_Eml")
JIRA_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")
TARGET_OBJECT_TYPE_ID = "450"

# Mapping
JIRA_ASSET_MAPPING = {
    "asset_type_name": "Asset Type",
    "asset_tag": "Asset Tag",
    "description": "Description",
    "end_of_life": "End of Life",
    "location_name": "Location",
    "department_name": "Department",
    "agent_name": "Managed By",
    "user_name": "Used By",
    "assigned_on": "Assigned On",
    "serial_number_26000466690": "Serial Number",
    "resolved_asset_state": "Asset State"
}

def get_jira_attribute_map():
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttype/{TARGET_OBJECT_TYPE_ID}/attributes"
    headers = {"Accept": "application/json", "X-ExperimentalApi": "opt-in"}
    res = requests.get(url, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)
    
    data = res.json()
    # FIX: Handle if 'data' is a list directly, or a dictionary containing 'values'
    attr_list = data.get("values", data) if isinstance(data, dict) else data
    
    mapping = {}
    for attr in attr_list:
        if "name" in attr and "id" in attr:
            mapping[attr["name"].lower().strip()] = attr["id"]
    return mapping

def find_asset_in_jira(serial, tag, name):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/aql/objects"
    headers = {"Accept": "application/json", "X-ExperimentalApi": "opt-in"}
    
    clauses = []
    if tag and str(tag).lower() != 'none': clauses.append(f'"Asset Tag" = "{tag}"')
    if serial and str(serial).lower() != 'none': clauses.append(f'"Serial Number" = "{serial}"')
    clauses.append(f'Name = "{name}"')
    
    aql = f'objectTypeId = {TARGET_OBJECT_TYPE_ID} AND (' + " OR ".join(clauses) + ')'
    res = requests.get(url, params={"basicQuery": aql}, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)
    
    if res.status_code == 200:
        data = res.json().get("values", [])
        return data[0]["id"] if data else None
    return None

def update_asset(jira_id, payload):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/{jira_id}"
    headers = {"Content-Type": "application/json", "X-ExperimentalApi": "opt-in"}
    return requests.put(url, json={"attributes": payload}, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)

def run_sync():
    attr_map = get_jira_attribute_map()
    page = 1
    while True:
        print(f"[*] Fetching Freshservice page {page}...")
        assets = requests.get(f"https://{FS_DOMAIN}/api/v2/assets", 
                              auth=(FS_API_KEY, 'X'), 
                              params={"asset_type_id": FS_LAPTOP_TYPE_ID, "page": page},
                              verify=False).json().get("assets", [])
        if not assets: break
        
        for asset in assets:
            name = asset.get("name")
            tag = asset.get("asset_tag")
            # Pull from type_fields if missing in root
            serial = asset.get("serial_number") or asset.get("type_fields", {}).get("serial_number_26000466690")
            
            jira_id = find_asset_in_jira(serial, tag, name)
            if not jira_id:
                print(f"   [!] Skipping {name}: Not found in Jira.")
                continue
                
            print(f"   [+] Updating {name} (Jira ID: {jira_id})")
            payload = []
            for fs_key, jira_name in JIRA_ASSET_MAPPING.items():
                val = asset.get(fs_key) or asset.get("type_fields", {}).get(fs_key)
                if val and str(val).lower() != 'none':
                    attr_id = attr_map.get(jira_name.lower())
                    if attr_id:
                        payload.append({"objectTypeAttributeId": attr_id, "objectAttributeValues": [{"value": str(val)}]})
            
            if payload:
                update_asset(jira_id, payload)
        page += 1

if __name__ == "__main__":
    run_sync()