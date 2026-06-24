import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import urllib3

# Disable SSL warnings for Freshservice sandbox connectivity
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# Source Configuration (Freshservice)
FS_DOMAIN = os.getenv("Fs_Domain").rstrip('/')
FS_API_KEY = os.getenv("Fs_API_Key")
FS_LAPTOP_TYPE_ID = os.getenv("Fs_Laptop_Type_ID")

# Destination Configuration (Jira Cloud)
JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EML = os.getenv("Jira_Eml")
JIRA_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")

TARGET_OBJECT_TYPE_ID = "450"  # Laptops Container ID

# Local dynamic lookup caches to minimize Freshservice directory API stress
DEPARTMENT_CACHE = {}
LOCATION_CACHE = {}
USER_CACHE = {}
ASSET_TYPE_CACHE = {}

# =========================================================================
# DEFINED FIELD MAPPING CONFIGURATION
# Now uses the exact Freshservice field keys from your original list
# =========================================================================
JIRA_ASSET_MAPPING = {
    "asset_tag": {"name": "Asset Tag", "type": 0},
    "description": {"name": "Description", "type": 7},
    "end_of_life": {"name": "End of Life", "type": 4},
    "location_name": {"name": "Location", "type": 0},
    "department_name": {"name": "Department", "type": 0},
    "agent_name": {"name": "Managed By", "type": 0},
    "user_name": {"name": "Used By", "type": 0},
    "assigned_on": {"name": "Assigned On", "type": 4},
    "product_26000466690": {"name": "Product", "type": 0},
    "vendor_26000466690": {"name": "Vendor", "type": 0},
    "cost_26000466690": {"name": "Cost", "type": 2},
    "purchase_order_26000466690": {"name": "Purchase Order", "type": 0},
    "acquisition_date_26000466690": {"name": "Acquisition Date", "type": 4},
    "warranty_26000466690": {"name": "Warranty", "type": 1},
    "warranty_type_26000466690": {"name": "Warranty Type", "type": 0},
    "warranty_expiry_date_26000466690": {"name": "Warranty Expiry Date", "type": 4},
    "domain_26000466690": {"name": "Domain", "type": 0},
    "resolved_asset_state": {"name": "Asset State", "type": 0},
    "other_user_responsible_26000466690": {"name": "Other User Responsible", "type": 0},
    "serial_number_26000466690": {"name": "Serial Number", "type": 0},        # FIXED key
    "state_26000466695": {"name": "State", "type": 0},                        # FIXED key
    "provider_type_26000466695": {"name": "Provider", "type": 0}
}

# =========================================================================
# FRESHSERVICE REFERENCE RESOLUTION HELPERS (unchanged)
# =========================================================================
def resolve_fs_asset_type(type_id):
    if not type_id: return None
    if type_id in ASSET_TYPE_CACHE: return ASSET_TYPE_CACHE[type_id]
    
    url = f"https://{FS_DOMAIN}/api/v2/asset_types/{type_id}"
    res = requests.get(url, auth=(FS_API_KEY, 'X'), verify=False, timeout=10)
    if res.status_code == 200:
        name = res.json().get("asset_type", {}).get("name")
        ASSET_TYPE_CACHE[type_id] = name
        return name
    return None

def resolve_fs_department(dept_id):
    if not dept_id: return None
    if dept_id in DEPARTMENT_CACHE: return DEPARTMENT_CACHE[dept_id]
    
    url = f"https://{FS_DOMAIN}/api/v2/departments/{dept_id}"
    res = requests.get(url, auth=(FS_API_KEY, 'X'), verify=False, timeout=10)
    if res.status_code == 200:
        name = res.json().get("department", {}).get("name")
        DEPARTMENT_CACHE[dept_id] = name
        return name
    return None

def resolve_fs_location(loc_id):
    if not loc_id: return None
    if loc_id in LOCATION_CACHE: return LOCATION_CACHE[loc_id]
    
    url = f"https://{FS_DOMAIN}/api/v2/locations/{loc_id}"
    res = requests.get(url, auth=(FS_API_KEY, 'X'), verify=False, timeout=10)
    if res.status_code == 200:
        name = res.json().get("location", {}).get("name")
        LOCATION_CACHE[loc_id] = name
        return name
    return None

def resolve_fs_user(user_id):
    if not user_id: return None
    if user_id in USER_CACHE: return USER_CACHE[user_id]
    
    url = f"https://{FS_DOMAIN}/api/v2/agents/{user_id}"
    res = requests.get(url, auth=(FS_API_KEY, 'X'), verify=False, timeout=5)
    
    if res.status_code != 200:
        url = f"https://{FS_DOMAIN}/api/v2/requesters/{user_id}"
        res = requests.get(url, auth=(FS_API_KEY, 'X'), verify=False, timeout=5)
        
    if res.status_code == 200:
        user_data = res.json().get("agent") or res.json().get("requester") or {}
        first = user_data.get("first_name", "") or ""
        last = user_data.get("last_name", "") or ""
        name = f"{first} {last}".strip() or user_data.get("primary_email")
        USER_CACHE[user_id] = name
        return name
    return None

# =========================================================================
# MAIN ENGINE
# =========================================================================
def get_jira_attribute_id_map():
    print("Discovering active Attribute IDs from Jira layout...")
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttype/{TARGET_OBJECT_TYPE_ID}/attributes"
    headers = {"Accept": "application/json", "X-ExperimentalApi": "opt-in"}
    
    response = requests.get(url, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed fetching Jira fields map configuration: {response.text}")
        
    response_data = response.json()
    attributes = response_data.get("values", []) if isinstance(response_data, dict) else response_data
    if not attributes and isinstance(response_data, list):
        attributes = response_data

    id_map = {}
    for attr in attributes:
        if "name" in attr and "id" in attr:
            normalized_name = attr["name"].lower().strip()
            id_map[normalized_name] = attr["id"]
            if attr.get("label") is True:
                id_map["name_label_field_id"] = attr["id"]
                
    return id_map

def check_jira_duplicate_by_identifiers(serial_number, asset_tag, jira_field_map):
    """
    Looks up duplicates using the primary global AQL endpoint.
    Returns True if an asset match exists.
    """
    if not serial_number and not asset_tag:
        return False
        
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/aql/objects"
    headers = {"Content-Type": "application/json", "X-ExperimentalApi": "opt-in"}
    
    serial_attr_id = jira_field_map.get("serial number")
    tag_attr_id = jira_field_map.get("asset tag")
    
    aql_clauses = []
    if serial_number and serial_attr_id:
        escaped_serial = str(serial_number).replace('"', '\\"')
        aql_clauses.append(f'attr({serial_attr_id}) = "{escaped_serial}"')
    if asset_tag and tag_attr_id:
        escaped_tag = str(asset_tag).replace('"', '\\"')
        aql_clauses.append(f'attr({tag_attr_id}) = "{escaped_tag}"')
        
    if not aql_clauses:
        if serial_number: aql_clauses.append(f'"Serial Number" = "{serial_number}"')
        if asset_tag: aql_clauses.append(f'"Asset Tag" = "{asset_tag}"')

    aql_query = f'objectTypeId = {TARGET_OBJECT_TYPE_ID} AND (' + " OR ".join(aql_clauses) + ')'
    payload = {"qlQuery": aql_query, "includeAttributes": False}
    
    try:
        response = requests.post(url, json=payload, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers, timeout=10)
        
        if response.status_code == 200:
            found_objects = response.json().get("values", [])
            return len(found_objects) > 0
        else:
            print(f"   Duplicate check returned status {response.status_code}. Defaulting to false.")
            return False
            
    except Exception as e:
        print(f"   Error running identity check: {str(e)}. Defaulting to false.")
        return False

def fetch_freshservice_assets(page=1):
    print(f"[*] Querying page {page} from Freshservice...")
    url = f"https://{FS_DOMAIN}/api/v2/assets"
    params = {"asset_type_id": FS_LAPTOP_TYPE_ID, "per_page": 50, "page": page}  # increased per_page
    response = requests.get(url, auth=(FS_API_KEY, 'X'), params=params, verify=False, timeout=15)
    if response.status_code != 200:
        raise Exception(f"Freshservice fetch execution failed: {response.text}")
    return response.json().get("assets", [])

def migrate_assets():
    try:
        jira_field_map = get_jira_attribute_id_map()
        print(f"[*] Starting asset migration pipeline...\n")
        
        jira_post_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/create"
        headers = {"Content-Type": "application/json", "X-ExperimentalApi": "opt-in"}
        
        name_field_id = jira_field_map.get("name_label_field_id") or jira_field_map.get("name")
        if not name_field_id:
            print("Warning: Could not resolve mandatory 'Name' label attribute field in Jira schema.")
            return

        successfully_migrated = 0
        page = 1
        max_pages = 100  # safety limit, but we'll break when no more assets
        
        while page <= max_pages:
            fs_assets = fetch_freshservice_assets(page=page)
            
            if not fs_assets:
                print(f"No more assets found after page {page}. Migration complete.")
                break
                
            print(f"[*] Processing {len(fs_assets)} assets from page {page}...\n")
            
            for asset in fs_assets:
                asset_name = asset.get("name") or f"Laptop-{asset.get('display_id')}"
                print(f"Processing: '{asset_name}'")
                
                type_fields = asset.get("type_fields", {}) or {}
                
                # Resolve ID-based references to human-readable names
                resolved_references = {}
                if asset.get("asset_type_id"):
                    resolved_references["asset_type_name"] = resolve_fs_asset_type(asset.get("asset_type_id"))
                if asset.get("department_id"):
                    resolved_references["department_name"] = resolve_fs_department(asset.get("department_id"))
                if asset.get("location_id"):
                    resolved_references["location_name"] = resolve_fs_location(asset.get("location_id"))
                if asset.get("user_id"):
                    resolved_references["user_name"] = resolve_fs_user(asset.get("user_id"))
                if asset.get("agent_id"):
                    resolved_references["agent_name"] = resolve_fs_user(asset.get("agent_id"))

                # Asset State resolution fallback
                resolved_references["resolved_asset_state"] = (
                    asset.get("asset_state") or 
                    type_fields.get("state_26000466695") or 
                    type_fields.get("compute_type_26000466690")
                )

                # Merge all data sources
                fs_pool = {**asset, **type_fields, **resolved_references}
                
                serial_num = fs_pool.get("serial_number_26000466690") or asset.get("serial_number")
                asset_tag = fs_pool.get("asset_tag")
                
                # Duplicate check
                if check_jira_duplicate_by_identifiers(serial_num, asset_tag, jira_field_map):
                    print(f"   [SKIP] Asset '{asset_name}' (Serial: {serial_num}) already exists in Jira. Moving to next.")
                    continue
                
                # Start building attribute payload
                attributes_payload = []
                
                # 1. Name (mandatory)
                attributes_payload.append({
                    "objectTypeAttributeId": name_field_id,
                    "objectAttributeValues": [{"value": str(asset_name)}]
                })
                
                # 2. Static "Asset Type" = "Laptop"
                asset_type_attr_id = jira_field_map.get("asset type")
                if asset_type_attr_id:
                    attributes_payload.append({
                        "objectTypeAttributeId": asset_type_attr_id,
                        "objectAttributeValues": [{"value": "Laptop"}]
                    })
                else:
                    print("   Warning: 'Asset Type' attribute not found in Jira schema; skipping.")
                
                # 3. All mapped fields from Freshservice
                for fs_key, target_info in JIRA_ASSET_MAPPING.items():
                    if fs_key in fs_pool:
                        raw_val = fs_pool.get(fs_key)
                        if raw_val is None or str(raw_val).strip() == "":
                            continue
                        
                        target_attr_lowercase = target_info["name"].lower().strip()
                        if target_attr_lowercase in jira_field_map:
                            # Convert type if needed
                            try:
                                if target_info["type"] == 1:    # Integer
                                    typed_val = int(float(raw_val))
                                elif target_info["type"] == 2:  # Float/Double
                                    typed_val = float(raw_val)
                                else:
                                    typed_val = str(raw_val).strip()
                            except (ValueError, TypeError):
                                typed_val = str(raw_val).strip()
                                
                            attributes_payload.append({
                                "objectTypeAttributeId": jira_field_map[target_attr_lowercase],
                                "objectAttributeValues": [{"value": typed_val}]
                            })
                        else:
                            # Optional: log fields that aren't found in Jira
                            pass
                
                # Send to Jira
                payload = {
                    "objectTypeId": TARGET_OBJECT_TYPE_ID,
                    "attributes": attributes_payload
                }
                
                response = requests.post(jira_post_url, json=payload, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)
                
                if response.status_code in [200, 201]:
                    print(f"   Successfully migrated item into target Layout Schema.")
                    successfully_migrated += 1
                else:
                    print(f"   Error: {response.status_code} - {response.text}")
            
            page += 1
        
        print(f"\n[COMPLETE] Migration complete. Successfully migrated {successfully_migrated} assets.")
                
    except Exception as e:
        print(f"[ERROR] Migration execution sequence failed: {e}")

if __name__ == "__main__":
    migrate_assets()