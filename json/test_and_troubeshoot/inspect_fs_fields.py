import requests
import os
import csv
import json
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. CONFIGURATION
# ==========================================
FS_DOMAIN = os.getenv("Fs_Domain").rstrip('/').replace('https://', '').replace('http://', '')
FS_API_KEY = os.getenv("Fs_API_Key")

HEADERS = {"Accept": "application/json"}
AUTH = (FS_API_KEY, "X")

def main():
    print("🔍 Fetching Standard Fields from a Sample Hardware Asset...")
    
    # Fetch just 1 asset to see its structure
    url = f"https://{FS_DOMAIN}/api/v2/assets?per_page=1"
    response = requests.get(url, headers=HEADERS, auth=AUTH)
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        return

    asset = response.json().get('assets', [{}])[0]
    
    print(f"\n✅ Successfully fetched sample asset: {asset.get('name')}\n")
    print("="*70)
    print(" STANDARD FIELDS (Root Level JSON Keys)")
    print("="*70)
    
    fields_list = []
    
    # Loop through the top-level keys (Standard Fields)
    for key, value in asset.items():
        # Ignore the custom fields folder
        if key == 'type_fields':
            continue
            
        # Get the data type for display
        data_type = type(value).__name__
        if isinstance(value, dict):
            data_type = "Object (Nested)"
        elif isinstance(value, list):
            data_type = "List/Array"
            
        # Print to console
        print(f"🔹 {key:<25} | Type: {data_type:<15} | Sample Value: {str(value)[:40]}")
        
        # Add to list for CSV
        fields_list.append({
            "Freshservice JSON Key": key,
            "Data Type": data_type,
            "Sample Value": str(value)[:50]
        })

    # Export to CSV
    csv_filename = "standard_fields_only.csv"
    with open(csv_filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Freshservice JSON Key", "Data Type", "Sample Value"])
        writer.writeheader()
        writer.writerows(fields_list)
        
    print(f"\n✅ Saved {len(fields_list)} standard fields to {csv_filename}")

if __name__ == "__main__":
    main()