# ===========================================================================
# Freshservice Field Label                      | Field Key / Variable ID  
# ===========================================================================
#  • Acquisition Date                          | acquisition_date_26000466690
#  • Asset Tag                                 | asset_tag                
#  • Asset Type                                | asset_type_id            
#  • Assigned On                               | assigned_on              
#  • Availability Zone                         | cd_availability_zone_26000466690
#  • Building                                  | building_26000466690     
#  • Cost                                      | cost_26000466690         
#  • CPU Core Count                            | cpu_core_count_26000466695
#  • CPU Speed(GHz)                            | cpu_speed_26000466695    
#  • Creation Timestamp                        | creation_timestamp_26000466695
#  • Department                                | department_id            
#  • Depreciation Type                         | depreciation_id          
#  • Description                               | description              
#  • Disk Space(GB)                            | disk_space_26000466695   
#  • Display Name                              | name                     
#  • Domain                                    | domain_26000466690       
#  • End of Life                               | end_of_life              
#  • Floor                                     | floor_26000466690        
#  • Group                                     | group_id                 
#  • Hostname                                  | hostname_26000466695     
#  • Impact                                    | impact                   
#  • Instance Type                             | cd_instance_type_26000466695
#  • IP Address                                | computer_ip_address_26000466695
#  • Item ID                                   | item_id_26000466695      
#  • Item Name                                 | item_name_26000466695    
#  • Last Audit Date                           | last_audit_date_26000466690
#  • Last login by                             | last_login_by_26000466695
#  • Location                                  | location_id              
#  • MAC Address                               | mac_address_26000466695  
#  • Managed By                                | agent_id                 
#  • Memory(GB)                                | memory_26000466695       
#  • OS                                        | os_26000466695           
#  • OS Service Pack                           | os_service_pack_26000466695
#  • OS Version                                | os_version_26000466695   
#  • Other User Responsible                    | other_user_responsible_26000466690
#  • Physical Subtype                          | physical_subtype_26000466690
#  • Product                                   | product_26000466690      
#  • Provider                                  | provider_type_26000466695
#  • Public Address                            | public_address_26000466695
#  • Purchase Order                            | purchase_order_26000466690
#  • Region                                    | region_26000466690       
#  • Restricted Budget                         | restricted_budget_26000466690
#  • Room                                      | room_26000466690         
#  • Salvage                                   | salvage                  
#  • Serial Number                             | serial_number_26000466690
#  • State                                     | state_26000466695        
#  • Type                                      | compute_type_26000466690 
#  • Usage Type                                | usage_type               
#  • Used By                                   | user_id                  
#  • UUID                                      | uuid_26000466695         
#  • Vendor                                    | vendor_26000466690       
#  • Virtual Subtype                           | virtual_subtype_26000466690
#  • Warranty                                  | warranty_26000466690     
#  • Warranty Expiry Date                      | warranty_expiry_date_26000466690
#  • Warranty Type                             | warranty_type_26000466690
#  • Workspace                                 | workspace                
# ---------------------------------------------------------------------------


import requests
import urllib3

# Disable SSL warnings for sandbox connectivity
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Source Configuration (Freshservice)
FS_DOMAIN = "alliance.freshservice.com"
FS_API_KEY = "DbbbetkOM_FKsb-5s7c8"
TARGET_ASSET_TYPE_NAME = "Laptop"

def find_type_id_recursively(asset_types, target_name):
    """Traverses pages to find the targeted asset type structure ID"""
    for a_type in asset_types:
        if a_type.get("name", "").strip().lower() == target_name.lower():
            return a_type.get("id")
        sub_types = a_type.get("sub_asset_types", [])
        if sub_types:
            matched_id = find_type_id_recursively(sub_types, target_name)
            if matched_id:
                return matched_id
    return None

def get_laptop_fields():
    # 1. Page through asset types to find the accurate ID for Laptop
    all_types = []
    type_page = 1
    while True:
        url = f"https://{FS_DOMAIN}/api/v2/asset_types"
        response = requests.get(url, auth=(FS_API_KEY, 'X'), params={"page": type_page, "per_page": 100}, verify=False)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch asset types page {type_page}: {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        page_types = response.json().get("asset_types", [])
        if not page_types:
            break
        all_types.extend(page_types)
        type_page += 1

    print(f"Found {len(all_types)} total asset types")
    
    laptop_id = find_type_id_recursively(all_types, TARGET_ASSET_TYPE_NAME)
    if not laptop_id:
        print(f"ERROR: Could not resolve ID for asset type: '{TARGET_ASSET_TYPE_NAME}'")
        print(f"Available asset types: {[t.get('name') for t in all_types]}")
        return

    print(f"Found '{TARGET_ASSET_TYPE_NAME}' ID: {laptop_id}")
    print(f"Fetching all field configuration layout pages...\n")

    # 2. Query the fields schema endpoint looping through all pages
    all_fields_data = []
    field_page = 1
    max_pages = 50  # Safety limit
    
    while field_page <= max_pages:
        fields_url = f"https://{FS_DOMAIN}/api/v2/asset_types/{laptop_id}/fields"
        params = {"page": field_page, "per_page": 100}
        
        try:
            response = requests.get(fields_url, auth=(FS_API_KEY, 'X'), params=params, verify=False, timeout=10)
            
            if response.status_code != 200:
                print(f"ERROR: Failed to fetch fields page {field_page}: {response.status_code}")
                print(f"Response: {response.text}")
                break
                
            data = response.json()
            page_items = data.get("asset_type_fields", [])
            
            if not page_items:
                print(f"Fetched {len(all_fields_data)} total fields across {field_page - 1} pages")
                break
            
            # Each item has a "field_header" and nested "fields" array
            for item in page_items:
                field_header = item.get("field_header", "")
                nested_fields = item.get("fields", [])
                all_fields_data.extend(nested_fields)
            
            print(f"Page {field_page}: {len(page_items)} field groups")
            field_page += 1
            
        except requests.exceptions.Timeout:
            print(f"REQUEST TIMEOUT on page {field_page}. Stopping fetch.")
            break
        except Exception as e:
            print(f"ERROR on page {field_page}: {str(e)}")
            break
    
    print("\n" + "=" * 75)
    print(f"{'Freshservice Field Label':<45} | {'Field Key / Variable ID':<25}")
    print("=" * 75)
    
    # Deduplicate fields by name (same field appears multiple times across pages)
    unique_fields = {}
    for field in all_fields_data:
        field_key = field.get("name", "").strip()
        if field_key and field_key not in unique_fields:
            unique_fields[field_key] = field
    
    # Sort fields alphabetically by label for readability
    sorted_fields = sorted(unique_fields.values(), key=lambda x: x.get("label", "").lower().strip())

    for field in sorted_fields:
        label = field.get("label", "").strip()
        field_key = field.get("name", "").strip() 
        
        # Skip asset_state values filter tracking to keep lists distinct
        if field_key == "asset_state" or label.lower() == "asset state":
            continue

        print(f" • {label:<41} | {field_key:<25}")
        
    print("-" * 75)
    print(f"Total Unique Fields Discovered: {len(unique_fields)}")
    print(f"Total Raw Field Entries (before dedup): {len(all_fields_data)}")
    print("Use the 'Field Key' values above when writing custom matching dictionaries.")

if __name__ == "__main__":
    get_laptop_fields()