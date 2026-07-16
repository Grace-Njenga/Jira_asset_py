import requests
import os
from dotenv import load_dotenv

load_dotenv()

FS_DOMAIN = os.getenv("Fs_Domain").rstrip('/').replace('https://', '').replace('http://', '')
FS_API_KEY = os.getenv("Fs_API_Key")

HEADERS = {"Accept": "application/json"}
AUTH = (FS_API_KEY, "X")

def get_type_field_value(type_fields, base_key):
    """
    Searches type_fields for a key that starts with the base_key.
    This handles the '_26000466690' suffixes automatically.
    """
    # Exact match first
    if base_key in type_fields:
        return base_key, type_fields[base_key]
    # Suffix match (e.g., finds 'hostname_26000466695' when searching for 'hostname')
    for k, v in type_fields.items():
        if k.startswith(base_key + "_") or k == base_key:
            return k, v
    return None, None

def main():
    print("🔍 Fetching Assets to Test Specific Field Extraction...")
    
    # Fetch 10 assets to increase chances of finding ones with actual data
    url = f"https://{FS_DOMAIN}/api/v2/assets?per_page=10&include=type_fields"
    response = requests.get(url, headers=HEADERS, auth=AUTH)
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        return
        
    assets = response.json().get('assets', [])
    
    if not assets:
        print("No assets found.")
        return

    print(f"✅ Fetched {len(assets)} assets. Analyzing fields...\n")
    print("="*90)
    
    for i, asset in enumerate(assets):
        asset_name = asset.get('name', 'Unknown')
        print(f"\n📦 ASSET {i+1}: {asset_name}")
        print("-"*90)
        
        type_fields = asset.get('type_fields', {})
        
        # ==========================================
        # 1. ROOT LEVEL FIELDS
        # ==========================================
        print("  [ROOT LEVEL FIELDS]")
        root_fields = {
            "Name": "name",
            "Asset Type ID": "asset_type_id",
            "Description": "description",
            "End of Life": "end_of_life",
            "Location ID": "location_id",
            "Department ID": "department_id",
            "Agent ID": "agent_id",
            "Assigned On": "assigned_on"
        }
        
        for display_name, json_key in root_fields.items():
            val = asset.get(json_key)
            print(f"    {display_name:<20} (Key: '{json_key}') : {val}")
            
        # ==========================================
        # 2. TYPE_FIELDS LEVEL FIELDS
        # ==========================================
        print("\n  [TYPE_FIELDS LEVEL FIELDS]")
        tf_fields_to_find = [
            "last_login_by",
            "asset_state",
            "other_user_responsible",
            "hostname"
        ]
        
        for base_key in tf_fields_to_find:
            actual_key, val = get_type_field_value(type_fields, base_key)
            if actual_key:
                # Clean up the display name for printing
                display = base_key.replace('_', ' ').title()
                print(f"    {display:<25} (Key: '{actual_key}') : {val}")
            else:
                display = base_key.replace('_', ' ').title()
                print(f"    {display:<25} (Key: NOT FOUND)")

        print("="*90)

if __name__ == "__main__":
    main()