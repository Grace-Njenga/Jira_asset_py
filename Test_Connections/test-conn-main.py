import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

FS_DOMAIN = os.getenv("Fs_Domain")
FS_API_KEY = os.getenv("FS_Api_Key")
JIRA_URL = os.getenv("Jira_url").rstrip('/')
JIRA_EML = os.getenv("Jira_Eml")
JIRA_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")
SCHEMA_ID = os.getenv("Object_schm_ID")

def test_freshservice():
    print("⏳ Testing Freshservice Connection...")
    # Using the asset type fields endpoint as a test for object 452
    url = f"https://{FS_DOMAIN}/api/v2/asset_types/"
    
    # Freshservice uses API key as username and dummy password 'X'
    response = requests.get(url, auth=HTTPBasicAuth(FS_API_KEY, "X"))
    
    if response.status_code == 200:
        print("✅ Freshservice: Connection Successful! Found asset type.")
        return True
    else:
        print(f"❌ Freshservice: Failed with status {response.status_code}")
        print(response.text)
        return False

def test_jira():
    print("\n⏳ Testing Jira Assets Connection...")
    # Endpoint to fetch details of the specific object schema
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objectschema/list"
    
    headers = {
        "Accept": "application/json",
        "X-ExperimentalApi": "opt-in"  # Often required for Assets REST API
    }
    
    response = requests.get(
        url, 
        auth=HTTPBasicAuth(JIRA_EML, JIRA_TOKEN), 
        headers=headers
    )
    
    if response.status_code == 200:
        print(f"✅ Jira Assets: Connection Successful! Found Schema ID: {SCHEMA_ID}")
        return True
    else:
        print(f"❌ Jira Assets: Failed with status {response.status_code}")
        print(response.text)
        return False

if __name__ == "__main__":
    fs_ok = test_freshservice()
    jira_ok = test_jira()
    
    if fs_ok and jira_ok:
        print("\n🎉 All systems go! You are ready to run the attribute creator script.")
    else:
        print("\n⚠️ Please fix the connection errors above before proceeding.")