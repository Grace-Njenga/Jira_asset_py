import json
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

# Attribute Mapping (Your actual IDs)
JIRA_ATTR_IDS = {
    "Name": 226,
    "Serial Number": 227,
    "Cost": 228,
    "End of Life": 229,
    "Asset Tag": 230,
    # "Department": 231,
    # "Used By (Name)": 232,
    "Used By": 233,
    # "Asset Type": 234,
    "Assigned on": 235,
    "Asset State": 236,
    "Last Login By": 237,
    # "Region": 238,
    # "Location": 239,
    "Other User Responsible": 240,
    "Warranty Expiry Date": 241,
    "Warranty Type": 242,
    "Warranty": 243,
    "Description": 244,
    "Room": 245,
    "Product": 246,
}

# File Export Settings
CSV_FILENAME = "skipped_assets_no_serial.csv"
LOG_FILENAME = "daily_sync_log.txt"
STATE_FILENAME = "migration_state.json"

# ==========================================
# 2. HELPER FUNCTIONS & CACHES
# ==========================================

location_cache = {}
department_cache = {}
user_cache = {}
asset_type_cache = {}
jira_attribute_name_cache = {}

def get_location_name(location_id):
    if not location_id: return None
    if location_id in location_cache: return location_cache[location_id]
    
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
    if department_id in department_cache: return department_cache[department_id]
    
    url = f"https://{FS_DOMAIN}/api/v2/departments/{department_id}"
    response = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth())
    if response.status_code == 200:
        name = response.json().get('department', {}).get('name')
        department_cache[department_id] = name
        time.sleep(0.2)
        return name
    return None

def get_fs_user_details(user_id):
    """Fetches user email and name, using cache and /requesters/ fallback."""
    if not user_id: return None
    if user_id in user_cache: return user_cache[user_id]
    
    # Try standard users endpoint
    url = f"https://{FS_DOMAIN}/api/v2/users/{user_id}"
    res = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth())
    if res.status_code == 200:
        user_data = res.json().get('user', {})
        user_cache[user_id] = user_data
        time.sleep(0.2)
        return user_data
        
    # Fallback to requesters endpoint
    url2 = f"https://{FS_DOMAIN}/api/v2/requesters/{user_id}"
    res2 = requests.get(url2, headers=get_fs_headers(), auth=get_fs_auth())
    if res2.status_code == 200:
        user_data = res2.json().get('requester', {})
        user_cache[user_id] = user_data
        time.sleep(0.2)
        return user_data
        
    return None


def normalize_attr_name(value):
    if not value:
        return ""
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        value = str(value)
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def resolve_fs_user_value(fs_asset, prefer_name=False):
    values_to_try = []

    for key in ["user_id", "assigned_to", "assigned_user_id", "requester_id", "requested_by_id", "owner_id"]:
        value = fs_asset.get(key)
        if value is not None and value != "":
            values_to_try.append(value)

    type_fields = fs_asset.get("type_fields", {}) or {}
    for key in ["last_login_by", "used_by", "user", "requester", "owner", "assigned_to"]:
        if key in type_fields and type_fields[key] not in [None, ""]:
            values_to_try.append(type_fields[key])

    for key in ["user_email", "assigned_to_email", "requester_email", "user_name", "assigned_to_name", "requester_name"]:
        value = fs_asset.get(key)
        if value not in [None, ""]:
            values_to_try.append(value)

    for key in ["user_email", "assigned_to_email", "requester_email", "user_name", "assigned_to_name", "requester_name"]:
        value = type_fields.get(key)
        if value not in [None, ""]:
            values_to_try.append(value)

    for candidate in values_to_try:
        if isinstance(candidate, dict):
            email = candidate.get("email") or candidate.get("primary_email") or candidate.get("contact")
            if email:
                return email if not prefer_name else (candidate.get("name") or candidate.get("display_name") or email)
            if prefer_name:
                full_name = " ".join(filter(None, [candidate.get("first_name"), candidate.get("last_name")]))
                if full_name:
                    return full_name
                name = candidate.get("name") or candidate.get("display_name")
                if name:
                    return name
            continue

        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            user_data = get_fs_user_details(int(candidate))
            if user_data:
                if prefer_name:
                    fn = user_data.get("first_name", "")
                    ln = user_data.get("last_name", "")
                    full_name = f"{fn} {ln}".strip()
                    return full_name or user_data.get("name") or user_data.get("display_name")
                return user_data.get("email") or user_data.get("primary_email") or user_data.get("contact")
            continue

        if isinstance(candidate, str):
            candidate_text = candidate.strip()
            if not candidate_text:
                continue
            if "@" in candidate_text:
                return candidate_text
            if prefer_name:
                return candidate_text
            # if the string looks like an ID, try user lookup
            if candidate_text.isdigit():
                user_data = get_fs_user_details(int(candidate_text))
                if user_data:
                    return user_data.get("email") or user_data.get("primary_email") or user_data.get("contact")
            return candidate_text

    return None


def get_asset_type_name(asset_type_id):
    """Resolves Freshservice asset type ID to human-readable name.
    Tries direct lookup first, then list endpoint, caches result.
    Returns readable name or None if not found."""
    if not asset_type_id:
        return None
    if asset_type_id in asset_type_cache:
        cached = asset_type_cache[asset_type_id]
        return cached if cached != str(asset_type_id) else None

    url = f"https://{FS_DOMAIN}/api/v2/asset_types/{asset_type_id}"
    response = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth(), timeout=10)
    if response.status_code == 200:
        payload = response.json()
        name = payload.get('asset_type', {}).get('name') or payload.get('name')
        if name:
            asset_type_cache[asset_type_id] = name
            time.sleep(0.1)
            return name

    list_url = f"https://{FS_DOMAIN}/api/v2/asset_types"
    try:
        list_response = requests.get(list_url, headers=get_fs_headers(), auth=get_fs_auth(), timeout=15)
        if list_response.status_code == 200:
            for item in list_response.json().get('asset_types', []):
                if str(item.get('id')) == str(asset_type_id):
                    name = item.get('name') or item.get('label')
                    if name:
                        asset_type_cache[asset_type_id] = name
                        time.sleep(0.1)
                        return name
                    break
    except Exception as e:
        pass

    asset_type_cache[asset_type_id] = str(asset_type_id)
    return None

def get_fs_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}

def get_jira_headers():
    return {"Content-Type": "application/json", "Accept": "application/json", "X-ExperimentalApi": "opt-in"}

def get_jira_auth():
    return (JIRA_EMAIL, JIRA_API_TOKEN)

def get_fs_auth():
    return (FS_API_KEY, "X")

def get_fs_value(fs_asset, jira_attr_name):
    type_fields = fs_asset.get('type_fields', {})
    
    def get_tf(base_key):
        if base_key in type_fields: return type_fields[base_key]
        for k, v in type_fields.items():
            if k.startswith(base_key + "_"): return v
        return None

    # 1. ROOT LEVEL & SPECIFIC LOGIC
    if jira_attr_name == "Name":
        return fs_asset.get('name')
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
        val = fs_asset.get('asset_type_id') or fs_asset.get('asset_type')
        if not val:
            return None
        if isinstance(val, (int, str)) and str(val).isdigit():
            readable = get_asset_type_name(val)
            return readable or str(val)
        return str(val)
        
    # USER FIELDS (Used By & Used By Name)
    if jira_attr_name in ["Used By", "Used By (Name)"]:
        if jira_attr_name == "Used By":
            return resolve_fs_user_value(fs_asset, prefer_name=False)
        return resolve_fs_user_value(fs_asset, prefer_name=True)

    # 2. TYPE_FIELDS LEVEL FIELDS
    if jira_attr_name == "Serial Number": return get_tf('serial_number')
    if jira_attr_name == "Cost": return get_tf('cost')
    if jira_attr_name == "Asset State": return get_tf('asset_state')
    if jira_attr_name == "Last Login By": return get_tf('last_login_by')
    if jira_attr_name == "Region": return get_tf('region')
    if jira_attr_name == "Other User Responsible": return get_tf('other_user_responsible')
    if jira_attr_name == "Previous User": return get_tf('previous_user') or fs_asset.get('previous_user')
    if jira_attr_name == "Warranty Expiry Date":
        val = get_tf('warranty_expiry_date')
        if val and isinstance(val, str) and 'T' in val: return val.split('T')[0]
        return val
    if jira_attr_name == "Warranty Type": return get_tf('warranty_type')
    if jira_attr_name == "Warranty": return get_tf('warranty')

    # Fallback
    val = get_tf(jira_attr_name.lower().replace(" ", "_"))
    if val: return val
    return fs_asset.get(jira_attr_name.lower().replace(" ", "_"))

def init_csv():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, CSV_FILENAME)
    if not os.path.exists(csv_path):
        with open(csv_path, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["Asset Name", "Asset ID", "Used Identifier", "Reason Skipped"])
    return csv_path


def get_resume_state_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, STATE_FILENAME)


def load_resume_state():
    env_value = os.getenv("FS_RESUME_FROM") or os.getenv("RESUME_FROM")
    if env_value is not None:
        try:
            return max(0, int(str(env_value).strip()))
        except ValueError:
            pass

    state_path = get_resume_state_path()
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    resume_from = data.get('resume_from')
                    if isinstance(resume_from, int) and resume_from >= 0:
                        return resume_from
        except Exception:
            pass

    return 0


def save_resume_state(position):
    state_path = get_resume_state_path()
    with open(state_path, 'w', encoding='utf-8') as fh:
        json.dump({"resume_from": position, "updated_at": datetime.now().isoformat()}, fh)


def log_skip(csv_path, asset_name, asset_id, identifier, reason):
    with open(csv_path, mode='a', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([asset_name, asset_id, identifier, reason])

def find_asset_in_jira(identifier, fs_asset=None):
    """Scans the target Jira object type for an existing asset before creating a new one."""
    if not identifier and not fs_asset:
        return None

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    payload = {"qlQuery": f"objectTypeId = {OBJECT_TYPE_ID}"}

    response = requests.post(url, json=payload, headers=get_jira_headers(), auth=get_jira_auth())

    if response.status_code != 200:
        print(f"[!] Duplicate lookup failed: {response.status_code} - {response.text[:200]}")
        return None

    data = response.json()
    entries = data.get("values", []) if isinstance(data, dict) and "values" in data else data.get("objectEntries", [])

    possible_values = []
    if identifier:
        possible_values.append(str(identifier).strip())
    if fs_asset:
        for key in ["name", "asset_tag", "asset_id", "id"]:
            value = fs_asset.get(key)
            if value:
                possible_values.append(str(value).strip())
        serial_value = get_fs_value(fs_asset, "Serial Number")
        if serial_value:
            possible_values.append(str(serial_value).strip())

        type_fields = fs_asset.get("type_fields", {}) or {}
        for key in ["serial_number", "asset_tag", "name", "asset_id"]:
            value = type_fields.get(key)
            if value:
                possible_values.append(str(value).strip())

    unique_values = []
    for value in possible_values:
        if value and value not in unique_values:
            unique_values.append(value)

    for entry in entries:
        if not entry:
            continue

        entry_id = entry.get("id")
        if not entry_id:
            continue

        candidate_texts = []
        for key in ["label", "objectKey"]:
            raw_value = entry.get(key)
            if raw_value:
                candidate_texts.append(str(raw_value).strip())

        for attr in entry.get("attributes", []):
            values = attr.get("objectAttributeValues", [])
            for value_obj in values:
                for field_name in ["value", "displayValue", "searchValue"]:
                    raw_value = value_obj.get(field_name)
                    if raw_value:
                        candidate_texts.append(str(raw_value).strip())

        normalized_texts = {normalize_text(text) for text in candidate_texts if normalize_text(text)}

        for candidate in unique_values:
            normalized_candidate = normalize_text(candidate)
            if not normalized_candidate:
                continue
            if normalized_candidate in normalized_texts:
                return entry_id
            if any(normalized_candidate in text or text in normalized_candidate for text in normalized_texts if text):
                return entry_id

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

def get_jira_attribute_id_map():
    if jira_attribute_name_cache:
        return jira_attribute_name_cache

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttype/{OBJECT_TYPE_ID}/attributes"
    response = requests.get(url, headers=get_jira_headers(), auth=get_jira_auth(), timeout=20)

    if response.status_code != 200:
        return {}

    try:
        attributes = response.json()
    except ValueError:
        return {}

    if not isinstance(attributes, list):
        return {}

    for attr in attributes:
        name = attr.get("name")
        attr_id = attr.get("id")
        if name and attr_id is not None:
            jira_attribute_name_cache[normalize_attr_name(name)] = {"id": attr_id, "name": name}

    return jira_attribute_name_cache


def get_attribute_candidates():
    candidates = []
    seen = set()

    for attr_name, attr_id in JIRA_ATTR_IDS.items():
        key = normalize_attr_name(attr_name)
        if key not in seen:
            candidates.append((attr_name, attr_id))
            seen.add(key)

    for attr_data in get_jira_attribute_id_map().values():
        attr_name = attr_data.get("name")
        attr_id = attr_data.get("id")
        key = normalize_attr_name(attr_name)
        if attr_name and attr_id is not None and key not in seen:
            candidates.append((attr_name, attr_id))
            seen.add(key)

    return candidates


def build_missing_only_payload(fs_asset, jira_obj):
    attributes_to_update = []

    for attr_name, attr_id in get_attribute_candidates():
        if not is_jira_attribute_empty(jira_obj, attr_id):
            continue

        value = get_fs_value(fs_asset, attr_name)

        if value is None:
            continue

        if value == "":
            continue

        attributes_to_update.append({
            "objectTypeAttributeId": attr_id,
            "objectAttributeValues": [{"value": str(value)}]
        })

    return attributes_to_update

def create_asset_in_jira(fs_asset):
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/create"
    attributes = []
    
    for attr_name, attr_id in get_attribute_candidates():
        value = get_fs_value(fs_asset, attr_name)
            
        if value not in [None, ""]:
            attributes.append({
                "objectTypeAttributeId": attr_id,
                "objectAttributeValues": [{"value": str(value)}]
            })

    payload = {"objectTypeId": OBJECT_TYPE_ID, "attributes": attributes}
    response = requests.post(url, json=payload, headers=get_jira_headers(), auth=get_jira_auth())
    
    if response.status_code in [200, 201]:
        print(f"   [OK] CREATED: {fs_asset.get('name')}")
        return True
    else:
        print(f"   [FAILED] CREATE {fs_asset.get('name')}: {response.text[:150]}...")
        return False

def update_asset_in_jira(jira_object_id, fs_asset):
    jira_obj = get_jira_object_details(jira_object_id)
    if not jira_obj:
        print(f"   [ERROR] FAILED TO FETCH DETAILS for {fs_asset.get('name')}")
        return False

    payload_attributes = build_missing_only_payload(fs_asset, jira_obj)

    if not payload_attributes:
        print(f"   [SKIP] UPDATE: {fs_asset.get('name')} (All fields already populated in Jira)")
        return True

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/{jira_object_id}"
    payload = {"attributes": payload_attributes}
    
    response = requests.put(url, json=payload, headers=get_jira_headers(), auth=get_jira_auth())
    
    if response.status_code == 200:
        print(f"   [UPDATE] UPDATED MISSING FIELDS: {fs_asset.get('name')}")
        return True
    else:
        print(f"   [FAILED] UPDATE {fs_asset.get('name')}: {response.text[:150]}...")
        return False

# ==========================================
# 3. MAIN SYNC LOGIC
# ==========================================

def sync_assets():
    print("[*] Starting Freshservice to Jira Assets Sync...")
    
    csv_path = init_csv()
    print(f"[LOG] Skipped assets will be saved to: {csv_path}\n")

    resume_from = load_resume_state()
    if resume_from > 0:
        print(f"[INFO] Resuming from asset position {resume_from}")
    
    page = 1
    per_page = 100 
    
    total_created = 0
    total_updated = 0
    total_failed = 0
    total_skipped = 0
    asset_index = 0
    
    while True:
        url = f"{FS_URL}?page={page}&per_page={per_page}&include=type_fields"
        print(f"\n[FETCH] Fetching page {page} ({per_page} assets per page)...")
        
        response = requests.get(url, headers=get_fs_headers(), auth=get_fs_auth())
        
        if response.status_code != 200:
            print(f"[ERROR] Error fetching from Freshservice: {response.text}")
            break
            
        data = response.json()
        assets = data.get('assets', [])
        
        if not assets:
            print("[DONE] Reached the end of all assets in Freshservice.")
            break

        print(f"--- Processing {len(assets)} assets on page {page}... ---")
        
        for asset in assets:
            if asset_index < resume_from:
                asset_index += 1
                save_resume_state(asset_index)
                continue

            asset_name = asset.get('name', 'Unknown Name')
            asset_id = asset.get('id', 'Unknown ID')
            
            # 1. Get the actual Serial Number value
            serial_value = get_fs_value(asset, "Serial Number")
            if serial_value:
                serial_value = str(serial_value).strip()
            
            # 2. Determine the identifier to search Jira
            if serial_value:
                identifier = serial_value
            else:
                identifier = asset_name
                print(f"[INFO] No Serial Number for '{asset_name}'. Using Name to check for duplicates. Serial Number will be left blank in Jira.")

            if not identifier:
                log_skip(csv_path, asset_name, asset_id, "N/A", "Missing Both Serial Number and Name")
                print(f"[WARN] SKIPPED: {asset_name} (No Serial Number and No Name)")
                total_skipped += 1
                continue
                
            print(f"Processing: {asset_name} (Identifier: {identifier})")
            jira_id = find_asset_in_jira(identifier, asset)
            
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
            print(f"[PROGRESS] Progress: {current_progress} processed so far.\n")

            asset_index += 1
            save_resume_state(asset_index)
            
            # Rate Limiting: Pause for 1.0 seconds to avoid Jira API blocks
            time.sleep(1.0) 
            
        page += 1 

    # --- FINAL MIGRATION REPORT & LOGGING ---
    total_migrated = total_created + total_updated
    
    report = f"""
==================================================
🏁 MIGRATION COMPLETE! FINAL REPORT: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
==================================================
[OK] Total Successfully Migrated/Updated: {total_migrated}
   ➕ Newly Created in Jira:   {total_created}
   [SYNC] Updated Missing Fields:  {total_updated}
[FAIL] Total Failed:               {total_failed}
[WARN] Total Skipped:              {total_skipped}
==================================================
"""
    
    print(report)
    
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, LOG_FILENAME)
    
    with open(log_path, mode='a', encoding='utf-8') as log_file:
        log_file.write(report + "\n")
        
    print(f"[REPORT] Report saved to: {log_path}")

if __name__ == "__main__":
    sync_assets()