import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

JIRA_EML = os.getenv("Jira_Eml")
JIRA_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")

TARGET_OBJECT_TYPE_ID = "451"  # Laptops

# Data Type Mapping Matrix for Jira Cloud Assets Engine:
# 0 = Text, 1 = Integer, 2 = Float/Double, 4 = Date, 7 = Text Area (Multiline)
FIELDS_WITH_TYPES = {
    "Asset Type": 0, 
    "Asset Tag": 0, 
    "Description": 7,  # Set to multi-line Text Area
    "End of Life": 4,   # Date
    "Location": 0, 
    "Department": 0, 
    "Managed By": 0, 
    "Used By": 0, 
    "Assigned On": 4,   # Date
    "Product": 0, 
    "Vendor": 0, 
    "Cost": 2,          # Float/Double
    "Purchase Order": 0, 
    "Acquisition Date": 4, # Date
    "Warranty": 1,       # Integer
    "Warranty Type": 0, 
    "Warranty Expiry Date": 4, # Date
    "Domain": 0, 
    "Asset State": 0, 
    "Other User Responsible": 0, 
    "Serial Number": 0, 
    "State": 0, 
    "Provider": 0
}

def append_fields_with_types():
    print(f"🚀 Initializing typed schema mapping for Jira Object Type ID: {TARGET_OBJECT_TYPE_ID}...")
    
    # Cloud Gateway endpoint path
    url = f"https://api.atlassian.com/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttypeattribute/{TARGET_OBJECT_TYPE_ID}"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-ExperimentalApi": "opt-in"
    }
    
    for field_name, type_id in FIELDS_WITH_TYPES.items():
        payload = {
            "name": field_name,
            "description": "Synced attribute structure from Freshservice",
            "type": 0,             # 0 = Default core attribute classification
            "defaultTypeId": type_id  # Explicit native data format type integer
        }
        
        response = requests.post(
            url, 
            json=payload, 
            auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), 
            headers=headers
        )
        
        if response.status_code in [200, 201]:
            print(f"  ✅ Successfully appended: '{field_name}' (Type ID: {type_id})")
        elif response.status_code == 400 and "already exists" in response.text.lower():
            print(f"  ℹ️ Field '{field_name}' already exists on this layout. Skipping.")
        else:
            print(f"  ❌ Failed for '{field_name}': {response.status_code} - {response.text}")

if __name__ == "__main__":
    append_fields_with_types()