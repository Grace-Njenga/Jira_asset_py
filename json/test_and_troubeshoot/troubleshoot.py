import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

FS_DOMAIN = os.getenv("Fs_Domain").rstrip('/').replace('https://', '').replace('http://', '')
FS_API_KEY = os.getenv("Fs_API_Key")

HEADERS = {"Accept": "application/json"}
AUTH = (FS_API_KEY, "X")

def try_fetch(url, label):
    print(f"\n Trying {label}...")
    print(f"URL: {url}")
    response = requests.get(url, headers=HEADERS, auth=AUTH)
    
    if response.status_code == 200:
        data = response.json()
        # Handle both list and single object responses
        asset = data.get('asset') or data.get('assets', [{}])[0]
        
        if asset:
            print(f"✅ SUCCESS! Found asset: {asset.get('name')}")
            print(f"   serial_number: {asset.get('serial_number')}")
            print(f"   cost: {asset.get('cost')}")
            print(f"   state: {asset.get('state')}")
            print(f"   user: {asset.get('user')}")
            return asset
        else:
            print("❌ Returned 200 OK, but no asset data found in JSON.")
    else:
        print(f"❌ Failed. Status Code: {response.status_code}")
        
    return None

def main():
    print(" Troubleshooting Freshservice 404 Error...")
    
    # Step 1: Get the first asset from the list to get its IDs
    list_url = f"https://{FS_DOMAIN}/api/v2/assets?per_page=1"
    list_response = requests.get(list_url, headers=HEADERS, auth=AUTH)
    
    if list_response.status_code != 200:
        print(f"❌ Failed to fetch list: {list_response.status_code}")
        return
        
    asset_list = list_response.json().get('assets', [])
    if not asset_list:
        print("No assets found.")
        return
        
    asset = asset_list[0]
    internal_id = asset.get('id')
    display_id = asset.get('display_id') # The ID you see in the UI
    
    print(f"Found Asset: {asset.get('name')}")
    print(f"Internal ID: {internal_id}")
    print(f"Display ID: {display_id}")
    
    # Step 2: Try Method 1 - Standard Detail Endpoint with Internal ID
    asset_data = try_fetch(
        f"https://{FS_DOMAIN}/api/v2/assets/{internal_id}", 
        "Method 1: Standard Detail Endpoint (Internal ID)"
    )
    
    # Step 3: Try Method 2 - Filter Endpoint (Workaround for broken detail endpoints)
    if not asset_data:
        asset_data = try_fetch(
            f"https://{FS_DOMAIN}/api/v2/assets?filter=asset_id:{internal_id}", 
            "Method 2: Filter by Internal ID"
        )

    # Step 4: Try Method 3 - Filter by Display ID
    if not asset_data and display_id:
        asset_data = try_fetch(
            f"https://{FS_DOMAIN}/api/v2/assets?filter=display_id:{display_id}", 
            "Method 3: Filter by Display ID"
        )

    if asset_data:
        print("\n" + "="*70)
        print("✅ SUCCESS! We found the full data.")
        print("💡 Update your main script to use the URL format that worked above.")
        
        # Save the full JSON so you can see everything
        with open('successful_asset_dump.json', 'w', encoding='utf-8') as f:
            json.dump(asset_data, f, indent=4)
        print("Saved full JSON to 'successful_asset_dump.json'")
    else:
        print("\n" + "="*70)
        print("❌ ALL METHODS FAILED.")
        print(" This means your API key likely lacks 'Read' permissions for asset details.")
        print("   Go to Freshservice Admin -> API Settings and ensure your API key has full Asset Admin rights.")

if __name__ == "__main__":
    main()