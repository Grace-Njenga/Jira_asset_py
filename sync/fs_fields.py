# ⏳ Scanning Freshservice asset record for specific targets...

# 🔎 MATCHING RESULTS FOUND:
# ------------------------------------------------------------
# [Top-Level Base Fields]
#   🔹 Key: created_by_user                -> Value: None
#   🔹 Key: last_updated_by_user           -> Value: None
#   🔹 Key: location_id                    -> Value: None
#   🔹 Key: user_id                        -> Value: None

# [Type-Specific Fields (Laptop Attributes)]
#   (No matching keys found here)
# ------------------------------------------------------------

# 💡 TIP: If a field exists but is blank on this specific laptop record, its value will show as None/Empty.

import requests
import urllib3
import os
from dotenv import load_dotenv

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FS_DOMAIN = os.getenv("Fs_Domain")
FS_API_KEY = os.getenv("Fs_API_Key")
FS_LAPTOP_TYPE_ID = os.getenv("Fs_Laptop_Type_ID")

def check_specific_fields():
    print("⏳ Scanning Freshservice asset record for specific targets...")
    
    url = f"https://{FS_DOMAIN}/api/v2/assets"
    params = {
        "asset_type_id": FS_LAPTOP_TYPE_ID,
        "per_page": 1
    }
    
    try:
        response = requests.get(
            url, 
            auth=(FS_API_KEY, 'X'), 
            params=params,
            verify=False, 
            timeout=15
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch asset: {response.status_code} - {response.text[:200]}")
            return

        assets = response.json().get("assets", [])
        if not assets:
            print("ℹ️ No laptop assets found to inspect.")
            return
            
        asset = assets[0]
        type_fields = asset.get("type_fields", {})
        
        # Keywords we want to match against keys in the JSON payload
        targets = ["state", "status", "location", "region", "responsible", "warranty", "asset_state"]
        
        print("\n🔎 MATCHING RESULTS FOUND:")
        print("-" * 60)
        
        # 1. Check Native Fields
        print("[Top-Level Base Fields]")
        found_base = False
        for key, val in asset.items():
            if key != "type_fields" and any(t in key.lower() for t in targets):
                print(f"  🔹 Key: {key:<30} -> Value: {val}")
                found_base = True
        if not found_base:
            print("  (No matching keys found here)")

        # 2. Check Type-Specific Fields
        print("\n[Type-Specific Fields (Laptop Attributes)]")
        found_type = False
        for key, val in type_fields.items():
            if any(t in key.lower() for t in targets):
                print(f"  🔹 Key: {key:<30} -> Value: {val}")
                found_type = True
        if not found_type:
            print("  (No matching keys found here)")
            
        print("-" * 60)
        print("\n💡 TIP: If a field exists but is blank on this specific laptop record, its value will show as None/Empty.")

    except Exception as e:
        print(f"💥 Error checking fields: {e}")

if __name__ == "__main__":
    check_specific_fields()