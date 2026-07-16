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
    print("🔍 Fetching Asset with Exact Field Names...")
    
    # THE FIX: Added &include=type_fields to force Freshservice to send the hidden data
    url = f"https://{FS_DOMAIN}/api/v2/assets?per_page=1&include=type_fields"
    response = requests.get(url, headers=HEADERS, auth=AUTH)
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        return
        
    data = response.json()
    assets = data.get('assets', [])
    
    if not assets:
        print("No assets found.")
        return
        
    asset = assets[0]
    type_fields = asset.get('type_fields', {})
    
    print(f"\n✅ Successfully fetched: {asset.get('name')}")
    print("="*70)
    print(" EXACT FRESHSERVICE FIELD NAMES (Inside type_fields):")
    print("="*70)
    
    # 1. Check for "Serial Number" (Exact UI Name)
    print(f"\n🔹 'Serial Number': {type_fields.get('Serial Number')}")
    
    # 2. Check for "Used by" (Exact UI Name, no brackets)
    used_by_data = type_fields.get('Used by')
    print(f"\n🔹 'Used by' (Raw Data): {used_by_data}")
    
    # 3. If "Used by" is a dictionary, list ALL its contents
    if isinstance(used_by_data, dict):
        print("\n📂 FULL CONTENTS OF THE 'Used by' DICTIONARY:")
        print("-" * 40)
        for key, value in used_by_data.items():
            print(f"   {key}: {value}")
    else:
        print("   (Not a dictionary or empty)")

    # 4. FULL DUMP: Print the ENTIRE type_fields dictionary
    print("\n" + "="*70)
    print(" FULL 'type_fields' DICTIONARY DUMP:")
    print("="*70)
    for key, value in type_fields.items():
        # If the value is a dictionary (like Location, Department, etc.), print it nicely
        if isinstance(value, dict):
            print(f"🔹 {key}:")
            for sub_key, sub_val in value.items():
                print(f"      {sub_key}: {sub_val}")
        else:
            print(f"🔹 {key}: {value}")

if __name__ == "__main__":
    main()