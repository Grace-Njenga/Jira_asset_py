import requests
import os
from dotenv import load_dotenv

load_dotenv()

JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EMAIL = os.getenv("Jira_Eml")
JIRA_API_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")
ENV_OBJECT_TYPE_ID = os.getenv("JIRA_OBJECT_TYPE_ID")

JIRA_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
JIRA_AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)

def main():
    print(f"🔍 Step 1: Checking .env file...")
    print(f"   JIRA_OBJECT_TYPE_ID in .env is: {ENV_OBJECT_TYPE_ID}\n")
    
    # 1. Fetch details of the Object Type from .env
    print(f"🔍 Step 2: Fetching details for Object Type ID: {ENV_OBJECT_TYPE_ID}...")
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttype/{ENV_OBJECT_TYPE_ID}"
    res = requests.get(url, headers=JIRA_HEADERS, auth=JIRA_AUTH)
    
    ot_name = None
    if res.status_code == 200:
        ot_data = res.json()
        ot_name = ot_data.get('name')
        print(f"   ✅ Object Type Name is: '{ot_name}'")
        
        # 2. Search for objects using the EXACT name
        print(f"\n🔍 Step 3: Searching for objects with objectType = '{ot_name}'...")
        aql_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
        aql = f'objectType = "{ot_name}"'
        res2 = requests.post(aql_url, json={"qlQuery": aql}, headers=JIRA_HEADERS, auth=JIRA_AUTH)
        
        if res2.status_code == 200:
            entries = res2.json().get('objectEntries', [])
            print(f"   ✅ Found {len(entries)} objects in '{ot_name}'.")
            
            if len(entries) > 0:
                print("\n--- First 3 Objects in this Object Type ---")
                for i, obj in enumerate(entries[:3]):
                    print(f"   Object ID: {obj.get('id')} | Label: '{obj.get('label')}'")
                    for attr in obj.get('attributes', []):
                        if str(attr.get('objectTypeAttributeId')) == '3336':
                            val = attr.get('objectAttributeValues', [{}])[0].get('value', '')
                            print(f"      -> Attribute 3336 (Name) value: '{val}'")
                return # We found them, we can stop
            else:
                print("   ⚠️ Found 0 objects! Let's list ALL object types to find where they are...")
        else:
            print(f"   ❌ AQL Error: {res2.text[:200]}")
    else:
        print(f"   ❌ Failed to fetch Object Type details: {res.text[:200]}")
        
    # 3. List ALL Object Types in the workspace
    print("\n" + "="*70)
    print("🔍 Step 4: Listing ALL Object Types in the workspace...")
    schema_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objectschema/list"
    res_schemas = requests.get(schema_url, headers=JIRA_HEADERS, auth=JIRA_AUTH)
    
    if res_schemas.status_code != 200:
        print(f"❌ Failed to list schemas: {res_schemas.text[:200]}")
        return
        
    schemas = res_schemas.json().get('objectschemas', [])
    for schema in schemas:
        schema_id = schema['id']
        print(f"\n📂 Schema: {schema['name']} (ID: {schema_id})")
        
        ot_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objectschema/{schema_id}/objecttypes"
        res_ot = requests.get(ot_url, headers=JIRA_HEADERS, auth=JIRA_AUTH)
        if res_ot.status_code == 200:
            ots = res_ot.json()
            for ot in ots:
                ot_id = ot['id']
                ot_name_loop = ot['name']
                
                # Quick count of objects in this OT
                aql_url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
                aql = f'objectTypeId = {ot_id}'
                res_count = requests.post(aql_url, json={"qlQuery": aql}, headers=JIRA_HEADERS, auth=JIRA_AUTH)
                count = 0
                if res_count.status_code == 200:
                    count = len(res_count.json().get('objectEntries', []))
                    
                print(f"   🔹 Object Type: '{ot_name_loop}' (ID: {ot_id}) | Objects: {count}")
                
                # If this OT has objects, print the first 3 to see what they look like
                if count > 0:
                    for i, obj in enumerate(res_count.json().get('objectEntries', [])[:3]):
                        label = obj.get('label')
                        print(f"      -> Sample Object {i+1}: ID {obj['id']} | Label: '{label}'")
                        # Check if ABCIT03452L is in the label
                        if 'ABCIT03452L' in str(label):
                            print(f"         💡 FOUND IT! The label contains 'ABCIT03452L'!")

if __name__ == "__main__":
    main()