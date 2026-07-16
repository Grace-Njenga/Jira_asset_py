import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

FS_DOMAIN = os.getenv("Fs_Domain").rstrip('/').replace('https://', '').replace('http://', '')
FS_API_KEY = os.getenv("Fs_API_Key")

HEADERS = {"Accept": "application/json"}
AUTH = (FS_API_KEY, "X")

def main():
    print(" Fetching FULL details for a single asset...")
    
    # Step 1: Get the ID of the first asset
    list_url = f"https://{FS_DOMAIN}/api/v2/assets?per_page=1"
    list_response = requests.get(list_url, headers=HEADERS, auth=AUTH)
    
    if list_response.status_code != 200:
        print(f"❌ Failed to fetch asset list: {list_response.status_code}")
        return
        
    asset_list = list_response.json().get('assets', [])
    if not asset_list:
        print("No assets found.")
        return
        
    asset_id = asset_list[0]['id']
    asset_name = asset_list[0]['name']
    
    print(f"Found Asset: {asset_name} (ID: {asset_id})")
    print(f"Fetching full details from /api/v2/assets/{asset_id}...\n")

    # Step 2: Fetch the FULL details using the specific ID
    detail_url = f"https://{FS_DOMAIN}/api/v2/assets/{asset_id}"
    detail_response = requests.get(detail_url, headers=HEADERS, auth=AUTH)
    
    if detail_response.status_code != 200:
        print(f"❌ Failed to fetch asset details: {detail_response.status_code}")
        return

    full_asset = detail_response.json().get('asset', {})
    
    print("="*70)
    print(" FULL API RESPONSE FOR THIS ASSET")
    print("="*70)
    
    # Print the specific fields you were looking for
    print(f"Root 'serial_number': {full_asset.get('serial_number')}")
    print(f"Root 'cost': {full_asset.get('cost')}")
    print(f"Root 'state': {full_asset.get('state')}")
    print(f"Root 'user': {full_asset.get('user')}")
    
    print("\n--- TYPE_FIELDS ---")
    type_fields = full_asset.get('type_fields', {})
    if type_fields:
        for key, value in type_fields.items():
            print(f"  {key}: {value}")
    else:
        print("  (Empty)")

    print("\n--- FULL JSON DUMP (Saved to full_asset_dump.json) ---")
    # Save the whole thing to a file so you can read it easily
    with open('full_asset_dump.json', 'w', encoding='utf-8') as f:
        json.dump(full_asset, f, indent=4)
        
    print("✅ Saved complete JSON to 'full_asset_dump.json'. Open this file to see exactly what Freshservice is sending!")

if __name__ == "__main__":
    main()