# Scans and returns schema id and object type id for the target schema and object type in Jira Assets. This is useful for mapping and migrating assets from Freshservice to Jira Assets.

# ============================================================

# 📂 SCHEMA: People (ID: 74)
# ------------------------------------------------------------
#    └── 🖥️ Object Type: Department (ID: 272)
#    └── 🖥️ Object Type: Role (ID: 273)
#    └── 🖥️ Object Type: Employees (ID: 274)
#    └── 🖥️ Object Type: Location (ID: 275)

import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EML = os.getenv("Jira_Eml")
JIRA_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")

def discover_assets_infrastructure():
    print("⏳ Connecting to Jira Assets API Gateway...")
    
    # 1. Fetch all Schemas in the workspace
    schema_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objectschema/list"
    headers = {"Accept": "application/json", "X-ExperimentalApi": "opt-in"}
    
    response = requests.get(schema_url, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch schemas: {response.status_code} - {response.text}")
        return
        
    schemas = response.json().get("values", [])
    print(f"📋 Found {len(schemas)} Schema(s) in this workspace.\n")
    print("=" * 60)
    
    for schema in schemas:
        schema_id = schema.get("id")
        schema_name = schema.get("name")
        print(f"📂 SCHEMA: {schema_name} (ID: {schema_id})")
        print("-" * 60)
        
        # 2. For each schema, fetch its containing Object Types (like Laptops, Users, etc.)
        ot_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objectschema/{schema_id}/objecttypes"
        ot_response = requests.get(ot_url, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)
        
        if ot_response.status_code == 200:
            object_types = ot_response.json()
            if not object_types:
                print("   (No Object Types found inside this schema)")
            
            for ot in object_types:
                ot_id = ot.get("id")
                ot_name = ot.get("name")
                print(f"   └── 🖥️ Object Type: {ot_name} (ID: {ot_id})")
                
                # Highlight if this matches your target setup
                if str(schema_id) == "140" and str(ot_id) == "450":
                    print("       🌟 TARGET DESTINATION VERIFIED! Fetching Attribute field maps...")
                    fetch_attributes_for_type(ot_id)
        else:
            print(f"   ❌ Could not read Object Types for schema {schema_id}")
            
        print("=" * 60 + "\n")

def fetch_attributes_for_type(object_type_id):
    """Helper to instantly reveal structural attribute IDs for mapping"""
    attr_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttype/{object_type_id}/attribute"
    headers = {"X-ExperimentalApi": "opt-in"}
    
    res = requests.get(attr_url, auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), headers=headers)
    if res.status_code == 200:
        attributes = res.json()
        for attr in attributes:
            print(f"           🔹 Field: {attr.get('name')} ---> (Use ID: \"{attr.get('id')}\")")
    else:
        print("       ❌ Unable to fetch deep attribute ID keys.")

if __name__ == "__main__":
    discover_assets_infrastructure()