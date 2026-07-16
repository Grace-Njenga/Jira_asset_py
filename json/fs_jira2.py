import requests
import time
import csv
import os
from datetime import datetime
from dotenv import load_dotenv

# IMPORTANT: Load the environment variables from your .env file!
load_dotenv()

# ==========================================
# 1. CONFIGURATION
# ==========================================
# Source Configuration (Freshservice)
FS_DOMAIN = os.getenv("Fs_Domain").rstrip('/').replace('https://', '').replace('http://', '')
FS_API_KEY = os.getenv("Fs_API_Key")
FS_URL = f"https://{FS_DOMAIN}/api/v2/assets"

# Jira Assets Details
JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EMAIL = os.getenv("Jira_Eml")
JIRA_API_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")
OBJECT_TYPE_ID = int(os.getenv("JIRA_OBJECT_TYPE_ID")) 

# Attribute Mapping (Freshservice Field Name -> Jira Attribute ID)
JIRA_ATTR_IDS = {
    "Hostname": 3336,
    "Serial Number": 3362,
    "Cost": 3353,
    "End of Life": 3340,
    "Asset Tag": 3338,
    "Department": 3346,
    "Used By": 3348,                # Email
    "Used By (Name)": 3380,          # Full Name
    "Asset Type": 3337,
    "Assigned on": 3350,
    "Asset State": 3360,
    "Last Login By": 3377,
    "Region": 3367,
    "Location": 3345,
    "Other User Responsible": 3361,
    "Previous User": 3382,
    "Warranty Expiry Date": 3358,
    "Warranty Type": 3357,
    "Warranty": 3356
}

# File Export Settings
CSV_FILENAME = "skipped_assets_no_serial.csv"
LOG_FILENAME = "daily_sync_log.txt"

# TEST MODE: Set to 5 to test. Change to None for full migration.
TEST_LIMIT = 3 # Set to None for full migration, or a number for testing

# ==========================================
# 2. HELPER FUNCTIONS & CACHES
# ==========================================

location_cache = {}
department_cache = {}
user_cache = {}

def get_fs_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}

def get_jira_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}

def get_jira_auth():
    return (JIRA_EMAIL, JIRA_API_TOKEN)

def get_fs_auth():
    return (FS_API_KEY, "X")

def get_location_name(location_id):
    if not location_id: return None
    if location_id in location_cache:
        return location_cache[location_id]
    url = f"https://{FS_DOMAIN}/api/v2/locations/{location_id}"
    response = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth())
    if response.status_code == 200:
        name = response.json().get('location', {}).get('name')
        location_cache[location_id] = name
        time.sleep(0.2)
        return name
    return None

def get_department_name(department_id):
    if not department_id: return None
    if department_id in department_cache:
        return department_cache[department_id]
    url = f"https://{FS_DOMAIN}/api/v2/departments/{department_id}"
    response = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth())
    if response.status_code == 200:
        name = response.json().get('department', {}).get('name')
        department_cache[department_id] = name
        time.sleep(0.2)
        return name
    return None

def get_fs_user_details(user_id):
    """
    Fetches the full user details from Freshservice.
    Uses /requesters endpoint since /users returns 410 Deprecated.
    Returns a dict with 'email' and 'name' keys.
    """
    if not user_id: return None
    if user_id in user_cache:
        return user_cache[user_id]
    
    # Try /requesters endpoint (confirmed working)
    url = f"https://{FS_DOMAIN}/api/v2/requesters/{user_id}"
    response = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth())
    
    if response.status_code == 200:
        user_data = response.json().get('requester', {})
        email = user_data.get('email') or user_data.get('primary_email')
        fn = user_data.get('first_name', '')
        ln = user_data.get('last_name', '')
        full_name = f"{fn} {ln}".strip()
        if not full_name:
            full_name = user_data.get('name') or user_data.get('display_name')
        
        result = {"email": email, "name": full_name}
        user_cache[user_id] = result
        time.sleep(0.2)
        return result
    
    # Fallback: Try /agents endpoint (for internal IT staff)
    url2 = f"https://{FS_DOMAIN}/api/v2/agents/{user_id}"
    response2 = requests.get(url2, headers=get_fs_headers(), auth=get_fs_auth())
    if response2.status_code == 200:
        agent_data = response2.json().get('agent', {})
        email = agent_data.get('email')
        full_name = agent_data.get('occasional', False)
        fn = agent_data.get('first_name', '')
        ln = agent_data.get('last_name', '')
        full_name = f"{fn} {ln}".strip()
        
        result = {"email": email, "name": full_name}
        user_cache[user_id] = result
        time.sleep(0.2)
        return result
    
    return None

def get_fs_value(fs_asset, jira_attr_name):
    """
    Maps Jira Attribute Names to the exact Freshservice JSON structure.
    Handles root fields, type_fields with '_ID' suffixes, date formatting,
    and user lookups.
    """
    type_fields = fs_asset.get('type_fields', {})
    
    def get_tf(base_key):
        if base_key in type_fields:
            return type_fields[base_key]
        for k, v in type_fields.items():
            if k.startswith(base_key + "_"):
                return v
        return None

    # ==========================================
    # 1. USER FIELDS (Used By, Used By Name)
    # ==========================================
    if jira_attr_name in ["Used By", "Used By (Name)"]:
        user_id = fs_asset.get('user_id')
        user_details = get_fs_user_details(user_id)
        if user_details:
            if jira_attr_name == "Used By":
                return user_details.get('email')
            else:
                return user_details.get('name')
        
        # Fallback: If no user_id, try last_login_by
        last_login = get_tf('last_login_by')
        if last_login and jira_attr_name == "Used By (Name)":
            return last_login
        return None

    # ==========================================
    # 2. ROOT LEVEL FIELDS
    # ==========================================
    if jira_attr_name == "Hostname":
        return get_tf('hostname') or fs_asset.get('hostname')
        
    if jira_attr_name == "Asset Tag":
        return fs_asset.get('asset_tag')
        
    if jira_attr_name == "End of Life":
        val = fs_asset.get('end_of_life')
        if val and isinstance(val, str) and 'T' in val: return val.split('T')[0]
        return val
        
    if jira_attr_name == "Assigned on":
        val = fs_asset.get('assigned_on')
        if val and isinstance(val, str) and 'T' in val: return val.split('T')[0]
        return val
        
    if jira_attr_name == "Location":
        return get_location_name(fs_asset.get('location_id'))
        
    if jira_attr_name == "Department":
        return get_department_name(fs_asset.get('department_id'))
        
    if jira_attr_name == "Asset Type":
        val = fs_asset.get('asset_type_id')
        return str(val) if val else None

    # ==========================================
    # 3. TYPE_FIELDS LEVEL FIELDS (with suffixes)
    # ==========================================
    if jira_attr_name == "Serial Number":
        return get_tf('serial_number')
    if jira_attr_name == "Cost":
        return get_tf('cost')
    if jira_attr_name == "Asset State":
        return get_tf('asset_state')
    if jira_attr_name == "Last Login By":
        return get_tf('last_login_by')
    if jira_attr_name == "Region":
        return get_tf('region')
    if jira_attr_name == "Other User Responsible":
        return get_tf('other_user_responsible')
    if jira_attr_name == "Previous User":
        return get_tf('previous_user') or fs_asset.get('previous_user')
    if jira_attr_name == "Warranty Expiry Date":
        val = get_tf('warranty_expiry_date')
        if val and isinstance(val, str) and 'T' in val: return val.split('T')[0]
        return val
    if jira_attr_name == "Warranty Type":
        return get_tf('warranty_type')
    if jira_attr_name == "Warranty":
        return get_tf('warranty')

    # Fallback
    val = get_tf(jira_attr_name.lower().replace(" ", "_"))
    if val: return val
    return fs_asset.get(jira_attr_name.lower().replace(" ", "_"))

def init_csv():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, CSV_FILENAME)
    with open(csv_path, mode='w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Asset Name", "Asset ID", "Used Identifier", "Reason Skipped"])
    return csv_path

def log_skip(csv_path, asset_name, asset_id, identifier, reason):
    with open(csv_path, mode='a', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([asset_name, asset_id, identifier, reason])

def find_asset_in_jira(identifier):
    """Uses AQL to check if the asset already exists in Jira."""
    # Use the correct endpoint and payload key
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    
    # Search using the OBJECT_TYPE_ID from .env file
    # Search by Serial Number OR Hostname OR Name
    aql_query = f"objectTypeId = {OBJECT_TYPE_ID} AND (\"Serial Number\" = '{identifier}' OR \"Hostname\" = '{identifier}' OR \"Name\" = '{identifier}')"
    payload = {"qlQuery": aql_query}
    
    response = requests.post(url, json=payload, headers=get_jira_headers(), auth=get_jira_auth())
    
    if response.status_code == 200:
        data = response.json()
        entries = data.get('objectEntries', [])
        if entries and len(entries) > 0:
            return entries[0]['id']
    return None

def get_jira_object_details(jira_object_id):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/{jira_object_id}"
    response = requests.get(url, headers=get_jira_headers(), auth=get_jira_auth())
    if response.status_code == 200:
        return response.json()
    return None

def is_jira_attribute_empty(jira_obj, attr_id):
    for attr in jira_obj.get('attributes', []):
        if attr.get('objectTypeAttributeId') == attr_id:
            values = attr.get('objectAttributeValues', [])
            if values and values[0].get('value'):
                return False 
    return True 

def build_missing_only_payload(fs_asset, jira_obj):
    attributes_to_update = []

    for attr_name, attr_id in JIRA_ATTR_IDS.items():
        if not is_jira_attribute_empty(jira_obj, attr_id):
            continue 

        value = get_fs_value(fs_asset, attr_name)

        if value:
            attributes_to_update.append({
                "objectTypeAttributeId": attr_id,
                "objectAttributeValues": [{"value": str(value)}]
            })

    return attributes_to_update

def create_asset_in_jira(fs_asset):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/create"
    attributes = []
    
    for attr_name, attr_id in JIRA_ATTR_IDS.items():
        value = get_fs_value(fs_asset, attr_name)
            
        if value:
            attributes.append({
                "objectTypeAttributeId": attr_id,
                "objectAttributeValues": [{"value": str(value)}]
            })

    payload = {"objectTypeId": OBJECT_TYPE_ID, "attributes": attributes}
    response = requests.post(url, json=payload, headers=get_jira_headers(), auth=get_jira_auth())
    
    if response.status_code in [200, 201]:
        print(f"   ✅ CREATED: {fs_asset.get('name')}")
        return True
    else:
        print(f"   ❌ FAILED TO CREATE {fs_asset.get('name')}: {response.text[:200]}...") 
        return False

def update_asset_in_jira(jira_object_id, fs_asset):
    jira_obj = get_jira_object_details(jira_object_id)
    if not jira_obj:
        print(f"   ❌ FAILED TO FETCH DETAILS for {fs_asset.get('name')}")
        return False

    payload_attributes = build_missing_only_payload(fs_asset, jira_obj)

    if not payload_attributes:
        print(f"   ⏭️ SKIPPED UPDATE: {fs_asset.get('name')} (All fields already populated in Jira)")
        return True

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/{jira_object_id}"
    payload = {"attributes": payload_attributes}
    
    response = requests.put(url, json=payload, headers=get_jira_headers(), auth=get_jira_auth())
    
    if response.status_code == 200:
        print(f"   🔄 UPDATED MISSING FIELDS: {fs_asset.get('name')}")
        return True
    else:
        print(f"   ❌ FAILED TO UPDATE {fs_asset.get('name')}: {response.text[:200]}...")
        return False

# ==========================================
# 3. MAIN SYNC LOGIC
# ==========================================

def sync_assets():
    print(f"🚀 Starting Freshservice to Jira Assets Sync (TEST LIMIT: {TEST_LIMIT})...")
    
    csv_path = init_csv()
    print(f"📄 Skipped assets will be saved to: {csv_path}\n")
    
    page = 1
    per_page = 100 
    
    total_created = 0
    total_updated = 0
    total_failed = 0
    total_skipped = 0
    
    while True:
        url = f"{FS_URL}?page={page}&per_page={per_page}&include=type_fields"
        print(f"\n🔗 Fetching page {page} ({per_page} assets per page)...")
        
        response = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth())
        
        if response.status_code != 200:
            print(f"❌ Error fetching from Freshservice: {response.text}")
            break
            
        data = response.json()
        assets = data.get('assets', [])
        
        if not assets:
            print("✅ Reached the end of all assets in Freshservice.")
            break

        print(f"--- Processing {len(assets)} assets on page {page}... ---")
        
        for asset in assets:
            asset_name = asset.get('name', 'Unknown Name')
            asset_id = asset.get('id', 'Unknown ID')
            
            # Get Serial Number
            serial_value = get_fs_value(asset, "Serial Number")
            if serial_value:
                serial_value = str(serial_value).strip()
            
            # Determine identifier for Jira search
            if serial_value:
                identifier = serial_value
            else:
                identifier = asset_name
                print(f"ℹ️ No Serial Number for '{asset_name}'. Using Name to check for duplicates.")

            if not identifier:
                log_skip(csv_path, asset_name, asset_id, "N/A", "Missing Both Serial Number and Name")
                print(f"⚠️ SKIPPED: {asset_name} (No Serial Number and No Name)")
                total_skipped += 1
                continue
                
            print(f"Processing: {asset_name} (Identifier: {identifier})")
            jira_id = find_asset_in_jira(identifier)
            
            if jira_id:
                if update_asset_in_jira(jira_id, asset):
                    total_updated += 1
                else:
                    total_failed += 1
            else:
                if create_asset_in_jira(asset):
                    total_created += 1
                else:
                    total_failed += 1
            
            current_progress = total_created + total_updated + total_failed + total_skipped
            print(f"📈 Progress: {current_progress} processed so far.\n")
            
            # TEST MODE: Stop after X assets
            if TEST_LIMIT and current_progress >= TEST_LIMIT:
                print(f"🛑 TEST MODE: Reached limit of {TEST_LIMIT} assets. Stopping sync.")
                break
                
            time.sleep(1.0) 
            
        if TEST_LIMIT and current_progress >= TEST_LIMIT:
            break
            
        page += 1 

    # --- FINAL MIGRATION REPORT & LOGGING ---
    total_migrated = total_created + total_updated
    
    report = f"""
==================================================
🏁 MIGRATION COMPLETE! FINAL REPORT: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
==================================================
✅ Total Successfully Migrated/Updated: {total_migrated}
   ➕ Newly Created in Jira:   {total_created}
   🔄 Updated Missing Fields:  {total_updated}
❌ Total Failed:               {total_failed}
⚠️ Total Skipped:              {total_skipped}
==================================================
"""
    
    print(report)
    
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, LOG_FILENAME)
    
    with open(log_path, mode='a', encoding='utf-8') as log_file:
        log_file.write(report + "\n")
        
    print(f"📝 Report saved to: {log_path}")

if __name__ == "__main__":
    sync_assets()