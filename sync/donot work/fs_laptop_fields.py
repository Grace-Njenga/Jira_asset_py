import requests
import urllib3

# Disable SSL warnings for sandbox connectivity
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Source Configuration (Freshservice)
FS_DOMAIN = "alliance.freshservice.com"
FS_API_KEY = "DbbbetkOM_FKsb-5s7c8"
TARGET_ASSET_TYPE_NAME = "Laptop"

def find_type_id_recursively(asset_types, target_name):
    """Traverses pages to find the targeted asset type structure ID"""
    for a_type in asset_types:
        if a_type.get("name", "").strip().lower() == target_name.lower():
            return a_type.get("id")
        sub_types = a_type.get("sub_asset_types", [])
        if sub_types:
            matched_id = find_type_id_recursively(sub_types, target_name)
            if matched_id:
                return matched_id
    return None

def get_laptop_fields():
    # 1. Page through asset types to find the accurate ID for Laptop
    all_types = []
    type_page = 1
    while True:
        url = f"https://{FS_DOMAIN}/api/v2/asset_types"
        response = requests.get(url, auth=(FS_API_KEY, 'X'), params={"page": type_page, "per_page": 100}, verify=False)
        page_types = response.json().get("asset_types", [])
        if not page_types:
            break
        all_types.extend(page_types)
        type_page += 1

    laptop_id = find_type_id_recursively(all_types, TARGET_ASSET_TYPE_NAME)
    if not laptop_id:
        print(f"❌ Could not resolve ID for asset type: '{TARGET_ASSET_TYPE_NAME}'")
        return

    print(f"🎯 Found '{TARGET_ASSET_TYPE_NAME}' ID: {laptop_id}")
    print(f"⏳ Fetching all field configuration layout pages recursively...\n")

    # 2. Query the fields schema endpoint looping through all pages
    all_fields_data = []
    field_page = 1
    
    while True:
        fields_url = f"https://{FS_DOMAIN}/api/v2/asset_types/{laptop_id}/fields"
        params = {"page": field_page, "per_page": 100}
        
        response = requests.get(fields_url, auth=(FS_API_KEY, 'X'), params=params, verify=False, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch fields page {field_page}: {response.status_code}")
            break
            
        page_fields = response.json().get("asset_type_fields", [])
        if not page_fields:
            break  # Break out if the page is empty
            
        all_fields_data.extend(page_fields)
        field_page += 1
    
    print("=" * 75)
    print(f"{'Freshservice Field Label':<45} | {'Field Key / Variable ID':<25}")
    print("=" * 75)

    # Sort fields alphabetically by label for readability
    all_fields_data.sort(key=lambda x: x.get("label", "").lower().strip())

    for field in all_fields_data:
        label = field.get("label", "").strip()
        field_key = field.get("name", "").strip() 
        
        # Skip asset_state values filter tracking to keep lists distinct
        if field_key == "asset_state" or label.lower() == "asset state":
            continue

        print(f" • {label:<41} | {field_key:<25}")
        
    print("-" * 75)
    print(f"Total Unique Fields Discovered across all pages: {len(all_fields_data)}")
    print("💡 Use the 'Field Key' values above when writing custom matching dictionaries.")

if __name__ == "__main__":
    get_laptop_fields()