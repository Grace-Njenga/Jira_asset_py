import os
import sys
import json
import logging
import requests
from datetime import datetime

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("freshservice-jsm-sync")

# --- ENVIRONMENT SETUP & VALIDATION ---
FRESHSERVICE_API_KEY = os.getenv("Fs_API_KEY")
FRESHSERVICE_DOMAIN = os.getenv("Fs_Domain") # e.g. 'company'
JIRA_API_KEY = os.getenv("JIRA_TOKEN")
JIRA_USER_EMAIL = os.getenv("JIRA_EML")
JIRA_CLOUD_URL = os.getenv("JIRA_URL") # e.g. 'https://company.atlassian.net'
JIRA_OBJECT_TYPE_ID = os.getenv("JIRA_OBJECT_TYPE_ID") # The Target Insight Object Type ID

required_vars = [
    "FRESHSERVICE_API_KEY", "FRESHSERVICE_DOMAIN", 
    "JIRA_API_KEY", "JIRA_USER_EMAIL", "JIRA_CLOUD_URL", "JIRA_OBJECT_TYPE_ID"
]
missing_vars = [v for v in required_vars if not os.getenv(v)]
if missing_vars:
    logger.error(f"Missing required environment variables: {missing_vars}")
    sys.exit(1)

# Clean base URLs
fs_base_url = f"https://{FRESHSERVICE_DOMAIN.replace('.freshservice.com', '')}.freshservice.com/api/v2"
jira_base_url = JIRA_CLOUD_URL.rstrip('/')

# Define HTTP Auth Sessions
fs_session = requests.Session()
fs_session.auth = (FRESHSERVICE_API_KEY, "X")
fs_session.headers.update({"Content-Type": "application/json"})

jira_session = requests.Session()
jira_session.auth = (JIRA_USER_EMAIL, JIRA_API_KEY)
jira_session.headers.update({
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-ExperimentalApi": "opt-in"  # JSM Assets API v1 requirement
})

# Field Mapping Configuration
FIELD_MAPPING = [
  {"jiraAttribute": "Asset Type", "freshserviceKey": "asset_type_id", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Asset Tag", "freshserviceKey": "asset_tag", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Description", "freshserviceKey": "description", "typeId": 7, "defaultValue": None},
  {"jiraAttribute": "End of Life", "freshserviceKey": "end_of_life", "typeId": 4, "defaultValue": None},
  {"jiraAttribute": "Location", "freshserviceKey": "location_id", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Department", "freshserviceKey": "department_id", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Managed By", "freshserviceKey": "agent_id", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Used By", "freshserviceKey": "user_id", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Assigned On", "freshserviceKey": "assigned_on", "typeId": 4, "defaultValue": None},
  {"jiraAttribute": "Product", "freshserviceKey": "product_26000466690", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Vendor", "freshserviceKey": "vendor_26000466690", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Cost", "freshserviceKey": "cost_26000466690", "typeId": 2, "defaultValue": None},
  {"jiraAttribute": "Purchase Order", "freshserviceKey": "purchase_order_26000466690", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Acquisition Date", "freshserviceKey": "acquisition_date_26000466690", "typeId": 4, "defaultValue": None},
  {"jiraAttribute": "Warranty", "freshserviceKey": "warranty_26000466690", "typeId": 1, "defaultValue": None},
  {"jiraAttribute": "Warranty Type", "freshserviceKey": "warranty_type_26000466690", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Warranty Expiry Date", "freshserviceKey": "warranty_expiry_date_26000466690", "typeId": 4, "defaultValue": None},
  {"jiraAttribute": "Domain", "freshserviceKey": "domain_26000466690", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Asset State", "freshserviceKey": "usage_type", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Other User Responsible", "freshserviceKey": "other_user_responsible_26000466690", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Serial Number", "freshserviceKey": "serial_number_26000466690", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "State", "freshserviceKey": "state_26000466695", "typeId": 0, "defaultValue": None},
  {"jiraAttribute": "Provider", "freshserviceKey": "provider_type_26000466695", "typeId": 0, "defaultValue": None}
]

# --- DATATYPE TRANSFORMATION UTILS ---
def format_value(raw_val, type_id):
    """
    Coerces raw values into precise datatypes conforming to Jira Insight attribute specs:
    0: Text/Default, 1: Integer, 2: Float, 4: Date, 7: Textarea
    """
    if raw_val is None:
        return None
    try:
        if type_id == 1: # Integer
            return int(float(str(raw_val).strip()))
        elif type_id == 2: # Float
            return float(str(raw_val).strip())
        elif type_id == 4: # Date (Extract YYYY-MM-DD cleanly)
            val_str = str(raw_val).strip()
            if len(val_str) >= 10:
                parsed_date = val_str[:10]
                try:
                    datetime.strptime(parsed_date, "%Y-%m-%d")
                    return parsed_date
                except ValueError:
                    pass
            return val_str
        else: # Standard String or TextArea
            return str(raw_val).strip()
    except Exception as e:
        logger.warning(f"Failed mapping/casting value [{raw_val}] for typeId [{type_id}]: {e}")
        return str(raw_val)

def get_fs_field_value(asset, key):
    """
    Extracts asset fields regardless of nested or flat layout structures in FS Assets JSON.
    """
    if key in asset:
        return asset[key]
    # Custom properties are often stored in an inner 'attributes' object in FS
    attributes_block = asset.get('attributes', {})
    if key in attributes_block:
        return attributes_block[key]
    return None

# --- FETCH TARGET SCHEMAS FROM JSM ---
def get_jsm_attribute_mapping():
    """
    Retrieves attributes schema configuration mapping for JIRA_OBJECT_TYPE_ID 
    to resolve attribute names directly to their target schema IDs.
    """
    url = f"{jira_base_url}/rest/assets/1.0/objecttype/{JIRA_OBJECT_TYPE_ID}/attributes"
    logger.info(f"Fetching attribute configurations for Object Type ID {JIRA_OBJECT_TYPE_ID} from JSM...")
    resp = jira_session.get(url)
    resp.raise_for_status()
    
    attributes = resp.json()
    mapping = {attr["name"].lower().strip(): attr["id"] for attr in attributes}
    return mapping

# --- JIRA ASSETS OPERATIONS ---
def search_jsm_asset(asset_tag):
    """
    Determines if an asset with this Asset Tag already exists in the scope schema.
    """
    escaped_tag = asset_tag.replace('"', '\\"')
    aql = f'objectTypeId = {JIRA_OBJECT_TYPE_ID} AND "Asset Tag" = "{escaped_tag}"'
    url = f"{jira_base_url}/rest/assets/1.0/object/search"
    resp = jira_session.get(url, params={"ql": aql})
    resp.raise_for_status()
    
    results = resp.json().get("objectEntries", [])
    if results:
        return results[0] # Return matched object structure
    return None

def sync_asset_to_jira(fs_asset, attr_name_to_id):
    """
    Transforms flat asset models to structure payloads, querying for updates/inserts on the JSM end.
    """
    asset_tag = get_fs_field_value(fs_asset, "asset_tag")
    if not asset_tag:
        logger.warning(f"Asset ID {fs_asset.get('id')} has no valid 'asset_tag'. Skipping sync.")
        return False

    # Map schema fields dynamically
    attributes_payload = []
    for field in FIELD_MAPPING:
        jira_attr_name = field["jiraAttribute"]
        attr_id = attr_name_to_id.get(jira_attr_name.lower().strip())
        if not attr_id:
            # Attribute doesn't exist on current Target JSM schema
            continue

        raw_val = get_fs_field_value(fs_asset, field["freshserviceKey"])
        if raw_val is None:
            raw_val = field.get("defaultValue")

        val = format_value(raw_val, field["typeId"])
        if val is not None:
            attributes_payload.append({
                "objectTypeAttributeId": attr_id,
                "objectAttributeValues": [{"value": val}]
            })

    # Search for an existing record to run PUT or POST updates
    existing_jsm_asset = search_jsm_asset(asset_tag)
    
    payload = {
        "objectTypeId": str(JIRA_OBJECT_TYPE_ID),
        "attributes": attributes_payload
    }

    try:
        if existing_jsm_asset:
            object_id = existing_jsm_asset["id"]
            url = f"{jira_base_url}/rest/assets/1.0/object/{object_id}"
            logger.info(f"Updating JSM Object (ID: {object_id}) for Asset Tag: {asset_tag}")
            resp = jira_session.put(url, json=payload)
        else:
            url = f"{jira_base_url}/rest/assets/1.0/object/create"
            logger.info(f"Creating new JSM Object for Asset Tag: {asset_tag}")
            resp = jira_session.post(url, json=payload)
        
        if resp.status_code not in [200, 201]:
            logger.error(f"JSM Error executing transaction for {asset_tag}: {resp.status_code} - {resp.text}")
            return False
        return True
    except Exception as err:
        logger.error(f"Critical transaction exception on asset {asset_tag}: {err}")
        return False

# --- MAIN PIPELINE PIPELINE ---
def run_sync():
    logger.info("Starting synchronization run...")
    try:
        attr_name_to_id = get_jsm_attribute_mapping()
    except Exception as e:
        logger.error(f"Failed fetching target JSM Schema metadata: {e}")
        return

    success_count = 0
    fail_count = 0
    page = 1
    per_page = 100

    while True:
        logger.info(f"Fetching Freshservice Asset Page {page}...")
        url = f"{fs_base_url}/assets"
        resp = fs_session.get(url, params={"page": page, "per_page": per_page})
        
        if resp.status_code != 200:
            logger.error(f"Failed retrieving Freshservice assets: {resp.status_code} - {resp.text}")
            break

        data = resp.json()
        assets = data.get("assets", [])
        if not assets:
            logger.info("Reached the end of Freshservice Asset pages.")
            break

        for asset in assets:
            success = sync_asset_to_jira(asset, attr_name_to_id)
            if success:
                success_count += 1
            else:
                fail_count += 1

        page += 1

    logger.info("=== Sync Execution Report ===")
    logger.info(f"Successfully Synced: {success_count} assets")
    logger.info(f"Failed Syncs:        {fail_count} assets")

if __name__ == "__main__":
    run_sync()