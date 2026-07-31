import json
import requests
import time
import csv
import os
import socket
from datetime import datetime
from dotenv import load_dotenv
from requests.exceptions import RequestException
from urllib.parse import urlparse

# IMPORTANT: Load the environment variables from your .env file.
load_dotenv()

# ==========================================
# 1. CONFIGURATION
# ==========================================
# Source Configuration (Freshservice)
FS_DOMAIN = os.getenv("Fs_Domain", "").rstrip('/').replace('https://', '').replace('http://', '')
FS_API_KEY = os.getenv("Fs_API_Key")
FS_URL = f"https://{FS_DOMAIN}/api/v2/assets"

# Jira Assets Details
JIRA_URL = os.getenv("Jira_url", "").rstrip('/')
JIRA_EMAIL = os.getenv("Jira_Eml")
JIRA_API_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")
OBJECT_TYPE_ID = int(os.getenv("JIRA_OBJECT_TYPE_ID"))

# Base Attribute Mapping (known IDs from your current object type)
JIRA_ATTR_IDS = {
    "Name": 226,
    "Serial Number": 227,
    # "Cost": 228,
    # "End of Life": 229,
    "Asset Tag": 230,
    # "Department": 231,
    # "Used By (Name)": 232,
    # "Used By": 233,
    # "Asset Type": 234,
    # "Assigned on": 235,
    "Asset State": 236,
    "Last Login By": 237,
    # "Region": 238,
    # "Location": 239,
    # "Other User Responsible": 240,
    # "Warranty Expiry Date": 241,
    # "Warranty Type": 242,
    # "Warranty": 243,
    # "Description": 244,
    # "Room": 245,
    # "Product": 246,
    "MAC Address": 347,
    "Purchase Order": 348,
    "Acquisition Date": 394
}

# Extra attributes commonly useful for CMDB-style assets.
# These are matched by name against Jira object type attributes.
IMPORTANT_ATTRIBUTE_NAMES = [
    "Hostname",
    "Model",
    "Manufacturer",
    "Vendor",
    "Purchase Date",
    "Acquisition Date",
    "Created At",
    "Updated At",
    "Last Login By",
    "Previous User",
    "Operating System",
    "OS",
    "Lifecycle Status",
    "Product",
    "Category",
]

# File Export Settings
CSV_FILENAME = "skipped_assets_no_serial.csv"
LOG_FILENAME = "daily_sync_log.txt"
STATE_FILENAME = "migration_state.json"


def env_flag(name, default="0"):
    value = os.getenv(name, default)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


# Performance and compatibility controls
STATE_SAVE_EVERY = max(1, int(os.getenv("FS_STATE_SAVE_EVERY", "10")))
RESOLVE_OPTION_LABELS = env_flag("FS_RESOLVE_OPTION_LABELS", "0")
SKIP_ATTR_NAMES = {
    normalize.strip()
    for normalize in (os.getenv("JIRA_SKIP_ATTR_NAMES", "Used By (Name)").split(","))
    if normalize.strip()
}
REQUEST_RETRY_COUNT = max(1, int(os.getenv("FS_REQUEST_RETRY_COUNT", "3")))
REQUEST_RETRY_DELAY = float(os.getenv("FS_REQUEST_RETRY_DELAY", "1.2"))
FAIL_FAST_DNS = env_flag("FS_FAIL_FAST_DNS", "1")
DNS_PRECHECK = env_flag("FS_DNS_PRECHECK", "1")


# Debug logging is disabled by default for strict run mode.
DEBUG_MATCH = False

# ==========================================
# 2. HELPER FUNCTIONS & CACHES
# ==========================================

location_cache = {}
department_cache = {}
user_cache = {}
asset_type_cache = {}
jira_attribute_name_cache = {}
asset_type_field_option_cache = {}
serial_duplicate_cache = {}


def debug_log(message):
    if DEBUG_MATCH:
        print(f"[DEBUG] {message}")


def get_fs_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}


def get_jira_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-ExperimentalApi": "opt-in",
    }


def get_jira_auth():
    return (JIRA_EMAIL, JIRA_API_TOKEN)


def get_fs_auth():
    return (FS_API_KEY, "X")


def extract_host(url):
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def is_dns_resolution_error(exc):
    error_text = str(exc)
    markers = [
        "NameResolutionError",
        "getaddrinfo failed",
        "Failed to resolve",
        "Temporary failure in name resolution",
    ]
    return any(marker in error_text for marker in markers)


def check_dns_resolution(host, service_name):
    if not host:
        print(f"[ERROR] {service_name} host is empty; check your .env settings.")
        return False

    try:
        socket.getaddrinfo(host, 443)
        return True
    except OSError as exc:
        print(f"[ERROR] DNS lookup failed for {service_name} host '{host}': {exc}")
        return False


def request_with_retry(method, url, request_name="request", **kwargs):
    last_error = None
    host = extract_host(url)
    for attempt in range(1, REQUEST_RETRY_COUNT + 1):
        try:
            return requests.request(method, url, **kwargs)
        except RequestException as exc:
            last_error = exc

            if FAIL_FAST_DNS and is_dns_resolution_error(exc):
                host_hint = host or "unknown-host"
                print(f"[ERROR] {request_name} failed: DNS resolution error for host '{host_hint}' ({exc})")
                print("[HINT] Check internet/VPN/DNS connectivity and retry the sync.")
                return None

            if attempt < REQUEST_RETRY_COUNT:
                wait_seconds = REQUEST_RETRY_DELAY * attempt
                print(f"[WARN] {request_name} failed ({exc}). Retrying in {wait_seconds:.1f}s [{attempt}/{REQUEST_RETRY_COUNT}]...")
                time.sleep(wait_seconds)

    print(f"[ERROR] {request_name} failed after {REQUEST_RETRY_COUNT} attempts: {last_error}")
    return None


def normalize_attr_name(value):
    if not value:
        return ""
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        value = str(value)
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def escape_aql_literal(value):
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')


def safe_date_only(value):
    if value and isinstance(value, str) and "T" in value:
        return value.split("T")[0]
    return value


def get_location_name(location_id):
    if not location_id:
        return None
    if location_id in location_cache:
        return location_cache[location_id]

    url = f"https://{FS_DOMAIN}/api/v2/locations/{location_id}"
    response = request_with_retry(
        "GET",
        url,
        request_name=f"Freshservice location lookup {location_id}",
        headers=get_fs_headers(),
        auth=get_fs_auth(),
        timeout=20,
    )
    if response is None:
        return None
    if response.status_code == 200:
        name = response.json().get("location", {}).get("name")
        location_cache[location_id] = name
        time.sleep(0.1)
        return name
    return None


def get_department_name(department_id):
    if not department_id:
        return None
    if department_id in department_cache:
        return department_cache[department_id]

    url = f"https://{FS_DOMAIN}/api/v2/departments/{department_id}"
    response = request_with_retry(
        "GET",
        url,
        request_name=f"Freshservice department lookup {department_id}",
        headers=get_fs_headers(),
        auth=get_fs_auth(),
        timeout=20,
    )
    if response is None:
        return None
    if response.status_code == 200:
        name = response.json().get("department", {}).get("name")
        department_cache[department_id] = name
        time.sleep(0.1)
        return name
    return None


def get_fs_user_details(user_id):
    """Fetches user details from Freshservice, with /requesters fallback."""
    if not user_id:
        return None
    if user_id in user_cache:
        return user_cache[user_id]

    # Try standard users endpoint first.
    url = f"https://{FS_DOMAIN}/api/v2/users/{user_id}"
    res = request_with_retry(
        "GET",
        url,
        request_name=f"Freshservice user lookup {user_id}",
        headers=get_fs_headers(),
        auth=get_fs_auth(),
        timeout=20,
    )
    if res is None:
        return None
    if res.status_code == 200:
        user_data = res.json().get("user", {})
        user_cache[user_id] = user_data
        time.sleep(0.1)
        return user_data

    # Fallback to requesters endpoint.
    url2 = f"https://{FS_DOMAIN}/api/v2/requesters/{user_id}"
    res2 = request_with_retry(
        "GET",
        url2,
        request_name=f"Freshservice requester fallback {user_id}",
        headers=get_fs_headers(),
        auth=get_fs_auth(),
        timeout=20,
    )
    if res2 is None:
        return None
    if res2.status_code == 200:
        user_data = res2.json().get("requester", {})
        user_cache[user_id] = user_data
        time.sleep(0.1)
        return user_data

    return None


def resolve_fs_user_value(fs_asset, prefer_name=False):
    values_to_try = []

    for key in ["user_id", "assigned_to", "assigned_user_id", "requester_id", "requested_by_id", "owner_id"]:
        value = fs_asset.get(key)
        if value is not None and value != "":
            values_to_try.append(value)

    type_fields = fs_asset.get("type_fields", {}) or {}
    for key in ["last_login_by", "used_by", "user", "requester", "owner", "assigned_to"]:
        if key in type_fields and type_fields[key] not in [None, ""]:
            values_to_try.append(type_fields[key])

    for key in [
        "user_email",
        "assigned_to_email",
        "requester_email",
        "user_name",
        "assigned_to_name",
        "requester_name",
    ]:
        value = fs_asset.get(key)
        if value not in [None, ""]:
            values_to_try.append(value)

    for key in [
        "user_email",
        "assigned_to_email",
        "requester_email",
        "user_name",
        "assigned_to_name",
        "requester_name",
    ]:
        value = type_fields.get(key)
        if value not in [None, ""]:
            values_to_try.append(value)

    for candidate in values_to_try:
        if isinstance(candidate, dict):
            email = candidate.get("email") or candidate.get("primary_email") or candidate.get("contact")
            if email:
                if prefer_name:
                    return candidate.get("name") or candidate.get("display_name") or email
                return email
            if prefer_name:
                full_name = " ".join(filter(None, [candidate.get("first_name"), candidate.get("last_name")]))
                if full_name:
                    return full_name
                name = candidate.get("name") or candidate.get("display_name")
                if name:
                    return name
            continue

        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            user_data = get_fs_user_details(int(candidate))
            if user_data:
                if prefer_name:
                    fn = user_data.get("first_name", "")
                    ln = user_data.get("last_name", "")
                    full_name = f"{fn} {ln}".strip()
                    return full_name or user_data.get("name") or user_data.get("display_name")
                return user_data.get("email") or user_data.get("primary_email") or user_data.get("contact")
            continue

        if isinstance(candidate, str):
            candidate_text = candidate.strip()
            if not candidate_text:
                continue
            if "@" in candidate_text:
                return candidate_text
            if prefer_name:
                return candidate_text
            if candidate_text.isdigit():
                user_data = get_fs_user_details(int(candidate_text))
                if user_data:
                    return user_data.get("email") or user_data.get("primary_email") or user_data.get("contact")
            return candidate_text

    return None


def get_asset_type_name(asset_type_id):
    if not asset_type_id:
        return None
    if asset_type_id in asset_type_cache:
        cached = asset_type_cache[asset_type_id]
        return cached if cached != str(asset_type_id) else None

    url = f"https://{FS_DOMAIN}/api/v2/asset_types/{asset_type_id}"
    response = request_with_retry(
        "GET",
        url,
        request_name=f"Freshservice asset type lookup {asset_type_id}",
        headers=get_fs_headers(),
        auth=get_fs_auth(),
        timeout=20,
    )
    if response is None:
        return None
    if response.status_code == 200:
        payload = response.json()
        name = payload.get("asset_type", {}).get("name") or payload.get("name")
        if name:
            asset_type_cache[asset_type_id] = name
            time.sleep(0.1)
            return name

    list_url = f"https://{FS_DOMAIN}/api/v2/asset_types"
    list_response = request_with_retry(
        "GET",
        list_url,
        request_name="Freshservice asset types list",
        headers=get_fs_headers(),
        auth=get_fs_auth(),
        timeout=20,
    )
    if list_response is None:
        return None
    if list_response.status_code == 200:
        for item in list_response.json().get("asset_types", []):
            if str(item.get("id")) == str(asset_type_id):
                name = item.get("name") or item.get("label")
                if name:
                    asset_type_cache[asset_type_id] = name
                    time.sleep(0.1)
                    return name
                break

    asset_type_cache[asset_type_id] = str(asset_type_id)
    return None


def build_asset_type_field_option_cache(asset_type_id):
    """Builds option-id -> label maps per field for a Freshservice asset type."""
    if not asset_type_id:
        return {}

    cache_key = str(asset_type_id)
    if cache_key in asset_type_field_option_cache:
        return asset_type_field_option_cache[cache_key]

    option_map = {}
    page = 1

    while True:
        url = f"https://{FS_DOMAIN}/api/v2/asset_types/{asset_type_id}/fields"
        response = request_with_retry(
            "GET",
            url,
            request_name=f"Freshservice asset type fields {asset_type_id} page {page}",
            headers=get_fs_headers(),
            auth=get_fs_auth(),
            params={"page": page, "per_page": 100},
            timeout=30,
        )
        if response is None:
            break

        if response.status_code != 200:
            break

        groups = response.json().get("asset_type_fields", [])
        if not groups:
            break

        found_any_field = False
        for group in groups:
            for field in group.get("fields", []):
                found_any_field = True
                field_name = field.get("name")
                if not field_name:
                    continue

                field_key = normalize_attr_name(field_name)
                option_map.setdefault(field_key, {})

                candidate_option_lists = []
                for key in ["choices", "options", "dropdown_options", "picklist_options", "values"]:
                    value = field.get(key)
                    if isinstance(value, list):
                        candidate_option_lists.append(value)

                for options in candidate_option_lists:
                    for option in options:
                        if not isinstance(option, dict):
                            continue

                        label = (
                            option.get("label")
                            or option.get("value")
                            or option.get("name")
                            or option.get("text")
                        )
                        if label in [None, ""]:
                            continue

                        for id_key in ["id", "value", "key", "choice_id", "option_id"]:
                            raw_id = option.get(id_key)
                            if raw_id not in [None, ""]:
                                option_map[field_key][str(raw_id)] = str(label)

        if not found_any_field:
            break

        page += 1

    asset_type_field_option_cache[cache_key] = option_map
    return option_map


def resolve_fs_option_value(fs_asset, field_aliases, raw_value):
    """Resolves a numeric option value to its label using Freshservice field metadata."""
    if not RESOLVE_OPTION_LABELS:
        return raw_value

    if raw_value in [None, ""]:
        return raw_value

    value_text = str(raw_value).strip()
    if not value_text.isdigit():
        return raw_value

    asset_type_id = fs_asset.get("asset_type_id") or fs_asset.get("asset_type")
    option_map = build_asset_type_field_option_cache(asset_type_id)
    if not option_map:
        return raw_value

    normalized_aliases = [normalize_attr_name(alias) for alias in field_aliases]
    normalized_aliases += [normalize_attr_name(alias) for alias in field_aliases if not alias.endswith("_name")]

    for field_key in normalized_aliases:
        values_for_field = option_map.get(field_key, {})
        if value_text in values_for_field:
            return values_for_field[value_text]

    return raw_value


def get_fs_value(fs_asset, jira_attr_name):
    type_fields = fs_asset.get("type_fields", {}) or {}

    def get_tf(base_key):
        if base_key in type_fields:
            return type_fields[base_key]
        for key, value in type_fields.items():
            if key.startswith(base_key + "_"):
                return value
        return None

    def get_tf_values(base_key):
        values = []
        if base_key in type_fields and type_fields[base_key] not in [None, ""]:
            values.append(type_fields[base_key])
        for key, value in type_fields.items():
            if key.startswith(base_key + "_") and value not in [None, ""]:
                values.append(value)
        return values

    # Root-level and explicit mappings.
    if jira_attr_name == "Name":
        return fs_asset.get("name")
    if jira_attr_name == "Description":
        return fs_asset.get("description") or get_tf("description")
    if jira_attr_name == "Asset Tag":
        return fs_asset.get("asset_tag")
    if jira_attr_name == "End of Life":
        return safe_date_only(fs_asset.get("end_of_life"))
    if jira_attr_name == "Assigned on":
        return safe_date_only(fs_asset.get("assigned_on"))
    if jira_attr_name == "Location":
        return get_location_name(fs_asset.get("location_id"))
    if jira_attr_name == "Department":
        return get_department_name(fs_asset.get("department_id"))
    if jira_attr_name == "Asset Type":
        val = fs_asset.get("asset_type_id") or fs_asset.get("asset_type")
        if not val:
            return None
        if isinstance(val, (int, str)) and str(val).isdigit():
            readable = get_asset_type_name(val)
            return readable or str(val)
        return str(val)

    if jira_attr_name in ["Used By", "Used By (Name)"]:
        return resolve_fs_user_value(fs_asset, prefer_name=(jira_attr_name == "Used By (Name)"))

    # Common type-fields.
    if jira_attr_name == "Serial Number":
        return get_tf("serial_number")
    if jira_attr_name == "Cost":
        return get_tf("cost")
    if jira_attr_name == "Asset State":
        return get_tf("asset_state")
    if jira_attr_name == "Last Login By":
        return get_tf("last_login_by")
    if jira_attr_name == "Region":
        return get_tf("region")
    if jira_attr_name == "Other User Responsible":
        return get_tf("other_user_responsible")
    if jira_attr_name == "Previous User":
        return get_tf("previous_user") or fs_asset.get("previous_user")
    if jira_attr_name == "Warranty Expiry Date":
        return safe_date_only(get_tf("warranty_expiry_date"))
    if jira_attr_name == "Warranty Type":
        return get_tf("warranty_type")
    if jira_attr_name == "Warranty":
        return get_tf("warranty")
    if jira_attr_name == "Product":
        raw_product = get_tf("product") or fs_asset.get("product") or get_tf("item_name") or fs_asset.get("item_name")
        if raw_product in [None, ""]:
            return None

        resolved_product = resolve_fs_option_value(
            fs_asset,
            ["product", "product_name", "item_name"],
            raw_product,
        )
        return resolved_product
    if jira_attr_name == "Room":
        parts = []

        building_value = get_tf("building") or fs_asset.get("building")
        floor_value = get_tf("floor") or fs_asset.get("floor")
        room_value = get_tf("room") or fs_asset.get("room")

        # Resolve dropdown IDs to labels where needed.
        building_value = resolve_fs_option_value(fs_asset, ["building"], building_value)
        floor_value = resolve_fs_option_value(fs_asset, ["floor"], floor_value)
        room_value = resolve_fs_option_value(fs_asset, ["room"], room_value)

        for value in [building_value, floor_value, room_value]:
            if value not in [None, ""]:
                text_value = str(value).strip()
                if text_value and text_value not in parts:
                    parts.append(text_value)

        if parts:
            return ", ".join(parts)
        return None

    # Extra useful attribute names.
    important_map = {
        "Hostname": ["hostname"],
        "Model": ["model", "product_model"],
        "Manufacturer": ["manufacturer", "brand"],
        "Vendor": ["vendor", "supplier"],
        "Purchase Date": ["purchase_date", "acquisition_date", "procured_date"],
        "Acquisition Date": ["acquisition_date", "purchase_date"],
        "Created At": ["created_at", "created_time"],
        "Updated At": ["updated_at", "last_updated_at"],
        "Operating System": ["operating_system", "os", "os_version"],
        "OS": ["os", "operating_system", "os_version"],
        "Lifecycle Status": ["lifecycle_status", "status", "asset_state"],
        "Product": ["product", "product_name"],
        "Category": ["category", "asset_category", "type"],
    }

    for candidate_key in important_map.get(jira_attr_name, []):
        value = get_tf(candidate_key)
        if value not in [None, ""]:
            if "date" in candidate_key or candidate_key.endswith("_at"):
                return safe_date_only(value)
            return value

        root_value = fs_asset.get(candidate_key)
        if root_value not in [None, ""]:
            if "date" in candidate_key or candidate_key.endswith("_at"):
                return safe_date_only(root_value)
            return root_value

    # Generic fallback by normalized field name.
    fallback_key = jira_attr_name.lower().replace(" ", "_")
    value = get_tf(fallback_key)
    if value not in [None, ""]:
        return value
    return fs_asset.get(fallback_key)


def init_csv():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, CSV_FILENAME)
    if not os.path.exists(csv_path):
        with open(csv_path, mode="w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["Asset Name", "Asset ID", "Used Identifier", "Reason Skipped"])
    return csv_path


def get_resume_state_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, STATE_FILENAME)


def load_resume_state():
    env_value = os.getenv("FS_RESUME_FROM") or os.getenv("RESUME_FROM")
    if env_value is not None:
        try:
            return max(0, int(str(env_value).strip()))
        except ValueError:
            pass

    state_path = get_resume_state_path()
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    resume_from = data.get("resume_from")
                    if isinstance(resume_from, int) and resume_from >= 0:
                        return resume_from
        except Exception:
            pass

    return 0


def save_resume_state(position):
    state_path = get_resume_state_path()
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump({"resume_from": position, "updated_at": datetime.now().isoformat()}, fh)


def log_skip(csv_path, asset_name, asset_id, identifier, reason):
    with open(csv_path, mode="a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([asset_name, asset_id, identifier, reason])


def get_jira_attribute_id_map():
    if jira_attribute_name_cache:
        return jira_attribute_name_cache

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objecttype/{OBJECT_TYPE_ID}/attributes"
    response = request_with_retry(
        "GET",
        url,
        request_name="Jira attribute map fetch",
        headers=get_jira_headers(),
        auth=get_jira_auth(),
        timeout=30,
    )
    if response is None:
        print("[WARN] Could not fetch Jira attribute list due to connection errors.")
        return {}

    if response.status_code != 200:
        print(f"[WARN] Could not fetch Jira attribute list: {response.status_code} {response.text[:160]}")
        return {}

    try:
        attributes = response.json()
    except ValueError:
        print("[WARN] Jira attribute list is not valid JSON.")
        return {}

    if not isinstance(attributes, list):
        print("[WARN] Jira attribute list response is not a list.")
        return {}

    for attr in attributes:
        name = attr.get("name")
        attr_id = attr.get("id")
        if name and attr_id is not None:
            jira_attribute_name_cache[normalize_attr_name(name)] = {"id": attr_id, "name": name}

    return jira_attribute_name_cache


def get_attribute_candidates():
    """Return attribute (name, id) pairs from fixed mapping plus important discovered attrs."""
    candidates = []
    seen = set()

    # Start with known hard-mapped attributes.
    for attr_name, attr_id in JIRA_ATTR_IDS.items():
        key = normalize_attr_name(attr_name)
        if key not in seen:
            candidates.append((attr_name, attr_id))
            seen.add(key)

    # Add important attributes if they exist in this Jira object type.
    jira_attr_map = get_jira_attribute_id_map()
    important_keys = {normalize_attr_name(name) for name in IMPORTANT_ATTRIBUTE_NAMES}

    for normalized_name, attr_data in jira_attr_map.items():
        if normalized_name in important_keys and normalized_name not in seen:
            attr_name = attr_data.get("name")
            attr_id = attr_data.get("id")
            if attr_name and attr_id is not None:
                candidates.append((attr_name, attr_id))
                seen.add(normalized_name)

    return candidates


def extract_jira_entry_texts(entry):
    texts = []
    for key in ["label", "objectKey"]:
        raw_value = entry.get(key)
        if raw_value:
            texts.append(str(raw_value).strip())

    for attr in entry.get("attributes", []):
        values = attr.get("objectAttributeValues", [])
        for value_obj in values:
            for field_name in ["value", "displayValue", "searchValue"]:
                raw_value = value_obj.get(field_name)
                if raw_value:
                    texts.append(str(raw_value).strip())

    return texts


def get_lookup_attribute_names():
    """Return existing Jira attribute names to use in AQL identity lookup."""
    attr_map = get_jira_attribute_id_map()
    preferred = ["Serial Number", "Asset Name", "Name", "Asset Tag"]
    preferred_norm = {normalize_attr_name(name): name for name in preferred}

    existing = []
    for normalized_name, attr_data in attr_map.items():
        if normalized_name in preferred_norm:
            existing_name = attr_data.get("name")
            if existing_name:
                existing.append(existing_name)

    # Deterministic order by our preferred list.
    ordered = []
    existing_norm_to_name = {normalize_attr_name(name): name for name in existing}
    for name in preferred:
        n = normalize_attr_name(name)
        if n in existing_norm_to_name:
            ordered.append(existing_norm_to_name[n])

    return ordered


def build_lookup_aql_query(candidate):
    escaped = escape_aql_literal(str(candidate).strip())
    attr_names = get_lookup_attribute_names()

    clauses = [f"objectKey = \"{escaped}\""]
    for attr_name in attr_names:
        clauses.append(f"\"{attr_name}\" = \"{escaped}\"")

    return f"objectTypeId = {OBJECT_TYPE_ID} AND (" + " OR ".join(clauses) + ")"


def search_jira_entries_by_value(candidate, asset_name=None):
    """Search Jira Assets by exact value across key fields for this object type."""
    if candidate in [None, ""]:
        return []

    escaped = escape_aql_literal(str(candidate).strip())
    if not escaped:
        return []

    query = build_lookup_aql_query(candidate)

    debug_log(
        f"AQL lookup for asset '{asset_name or 'Unknown'}' candidate '{candidate}': {query}"
    )

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    payload = {"qlQuery": query}
    response = request_with_retry(
        "POST",
        url,
        request_name=f"Jira lookup by candidate {candidate}",
        json=payload,
        headers=get_jira_headers(),
        auth=get_jira_auth(),
        timeout=40,
    )
    if response is None:
        return []

    if response.status_code != 200:
        debug_log(
            f"AQL lookup failed for candidate '{candidate}': {response.status_code} {response.text[:180]}"
        )
        return []

    data = response.json()
    entries = data.get("values", []) if isinstance(data, dict) and "values" in data else data.get("objectEntries", [])
    if isinstance(entries, list):
        matched_ids = [str(entry.get("id")) for entry in entries if entry.get("id") is not None]
        debug_log(f"AQL result for candidate '{candidate}': matched IDs={matched_ids}")
    return entries if isinstance(entries, list) else []


def find_existing_object_by_attribute(attr_name, value, exclude_object_id=None):
    """Find an object by exact attribute value in the same object type."""
    if value in [None, ""]:
        return None

    cache_key = (attr_name, str(value).strip())
    if cache_key in serial_duplicate_cache:
        cached_id = serial_duplicate_cache[cache_key]
        if cached_id and (exclude_object_id is None or str(cached_id) != str(exclude_object_id)):
            return cached_id
        return None

    escaped = escape_aql_literal(str(value).strip())
    if not escaped:
        return None

    query = f"objectTypeId = {OBJECT_TYPE_ID} AND \"{attr_name}\" = \"{escaped}\""
    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    payload = {"qlQuery": query}
    response = request_with_retry(
        "POST",
        url,
        request_name=f"Jira duplicate attribute lookup {attr_name}",
        json=payload,
        headers=get_jira_headers(),
        auth=get_jira_auth(),
        timeout=40,
    )
    if response is None:
        serial_duplicate_cache[cache_key] = None
        return None

    if response.status_code != 200:
        serial_duplicate_cache[cache_key] = None
        return None

    data = response.json()
    entries = data.get("values", []) if isinstance(data, dict) and "values" in data else data.get("objectEntries", [])
    if not isinstance(entries, list):
        return None

    for entry in entries:
        entry_id = str(entry.get("id", ""))
        if not entry_id:
            continue
        serial_duplicate_cache[cache_key] = entry_id
        if exclude_object_id is not None and entry_id == str(exclude_object_id):
            continue
        return entry_id

    serial_duplicate_cache[cache_key] = None
    return None


def find_asset_in_jira(asset_name):
    """Find Jira object by exact asset name. Prefers 'Asset Name', falls back to 'Name'."""
    if not asset_name:
        return None

    lookup_value = str(asset_name).strip()
    escaped = escape_aql_literal(lookup_value)
    if not escaped:
        return None

    attr_map = get_jira_attribute_id_map()
    name_candidates = []
    for preferred in ["Asset Name", "Name"]:
        normalized = normalize_attr_name(preferred)
        if normalized in attr_map:
            name_candidates.append(attr_map[normalized].get("name") or preferred)

    if not name_candidates:
        name_candidates = ["Asset Name", "Name"]

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/aql"
    for lookup_field in name_candidates:
        query = f"objectTypeId = {OBJECT_TYPE_ID} AND \"{lookup_field}\" = \"{escaped}\""
        payload = {"qlQuery": query}
        response = request_with_retry(
            "POST",
            url,
            request_name=f"Jira asset lookup by {lookup_field}",
            json=payload,
            headers=get_jira_headers(),
            auth=get_jira_auth(),
            timeout=40,
        )
        if response is None:
            continue

        if response.status_code != 200:
            print(f"[!] {lookup_field} lookup failed: {response.status_code} - {response.text[:200]}")
            continue

        data = response.json()
        entries = data.get("values", []) if isinstance(data, dict) and "values" in data else data.get("objectEntries", [])
        if isinstance(entries, list) and entries:
            return entries[0].get("id")

    return None


def build_update_payload(fs_asset, jira_object_id):
    attributes_to_update = []

    for attr_name, attr_id in get_attribute_candidates():
        if attr_name in SKIP_ATTR_NAMES:
            continue

        value = get_fs_value(fs_asset, attr_name)
        if value in [None, ""]:
            continue

        # Guard unique fields from duplicate-value update failures.
        if attr_name == "Serial Number":
            existing_object = find_existing_object_by_attribute("Serial Number", value, exclude_object_id=jira_object_id)
            if existing_object is not None:
                print(
                    f"   [WARN] SKIP Serial Number for {fs_asset.get('name')}: value '{value}' already exists in Jira object {existing_object}."
                )
                continue

        attributes_to_update.append(
            {
                "objectTypeAttributeId": attr_id,
                "objectAttributeValues": [{"value": str(value)}],
            }
        )

    return attributes_to_update


def update_asset_in_jira(jira_object_id, fs_asset):
    payload_attributes = build_update_payload(fs_asset, jira_object_id)

    if not payload_attributes:
        print(f"   [SKIP] UPDATE: {fs_asset.get('name')} (No mapped values found in Freshservice)")
        return True

    url = f"{JIRA_URL}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/object/{jira_object_id}"
    payload = {"attributes": payload_attributes}
    response = request_with_retry(
        "PUT",
        url,
        request_name=f"Jira update asset {jira_object_id}",
        json=payload,
        headers=get_jira_headers(),
        auth=get_jira_auth(),
        timeout=30,
    )
    if response is None:
        print(f"   [FAILED] UPDATE {fs_asset.get('name')}: connection error during update")
        return False

    if response.status_code == 200:
        print(f"   [UPDATE] UPDATED FIELDS: {fs_asset.get('name')}")
        return True

    print(f"   [FAILED] UPDATE {fs_asset.get('name')}: {response.text[:160]}...")
    return False


# ==========================================
# 3. MAIN UPDATE-ONLY SYNC LOGIC
# ==========================================

def sync_assets_update_only():
    print("[*] Starting Freshservice -> Jira update-only sync...")
    print("[MODE] Update-only mode active: create is disabled.")

    csv_path = init_csv()
    print(f"[LOG] Skipped assets will be saved to: {csv_path}\n")

    resume_from = load_resume_state()
    if resume_from > 0:
        print(f"[INFO] Resuming from asset position {resume_from}")

    if SKIP_ATTR_NAMES:
        print("[INFO] Skipping Jira attributes:", ", ".join(sorted(SKIP_ATTR_NAMES)))

    if not RESOLVE_OPTION_LABELS:
        print("[INFO] Option label resolution disabled (FS_RESOLVE_OPTION_LABELS=0) for faster sync.")

    # Build candidate list once and show what will be attempted.
    candidate_attrs = get_attribute_candidates()
    print(f"[INFO] Attribute candidates for missing-field updates: {len(candidate_attrs)}")
    print("[INFO] Attributes:", ", ".join(name for name, _ in candidate_attrs))

    page = 1
    per_page = 100

    total_updated = 0
    total_not_found = 0
    total_failed = 0
    total_skipped = 0
    asset_index = 0
    run_aborted_reason = None

    if DNS_PRECHECK:
        jira_host = extract_host(JIRA_URL)
        freshservice_host = FS_DOMAIN
        jira_ok = check_dns_resolution(jira_host, "Jira")
        freshservice_ok = check_dns_resolution(freshservice_host, "Freshservice")
        if not jira_ok or not freshservice_ok:
            run_aborted_reason = "DNS precheck failed for one or more required hosts"
            print(f"[ERROR] {run_aborted_reason}. Aborting before processing assets.")

    if run_aborted_reason is None:
        while True:
            url = f"{FS_URL}?page={page}&per_page={per_page}&include=type_fields"
            print(f"\n[FETCH] Fetching page {page} ({per_page} assets per page)...")

            response = request_with_retry(
                "GET",
                url,
                request_name=f"Freshservice assets page {page}",
                headers=get_fs_headers(),
                auth=get_fs_auth(),
                timeout=40,
            )
            if response is None:
                run_aborted_reason = "Freshservice page fetch failed due to repeated connection errors"
                print("[ERROR] Failed fetching from Freshservice due to repeated connection errors. Stopping run.")
                break
            if response.status_code != 200:
                run_aborted_reason = f"Freshservice page fetch failed: HTTP {response.status_code}"
                print(f"[ERROR] Error fetching from Freshservice: {response.status_code} {response.text[:200]}")
                break

            data = response.json()
            assets = data.get("assets", [])

            if not assets:
                print("[DONE] Reached the end of Freshservice assets.")
                break

            print(f"--- Processing {len(assets)} assets on page {page}... ---")

            for asset in assets:
                if asset_index < resume_from:
                    asset_index += 1
                    if asset_index % STATE_SAVE_EVERY == 0:
                        save_resume_state(asset_index)
                    continue

                asset_name = asset.get("name", "Unknown Name")
                asset_id = asset.get("id", "Unknown ID")

                cleaned_asset_name = str(asset_name).strip() if asset_name else ""
                if not cleaned_asset_name or cleaned_asset_name.lower() == "unknown name":
                    log_skip(csv_path, asset_name, asset_id, "N/A", "Missing Asset Name")
                    print(f"[WARN] SKIPPED: {asset_name} (No usable Asset Name)")
                    total_skipped += 1
                    asset_index += 1
                    if asset_index % STATE_SAVE_EVERY == 0:
                        save_resume_state(asset_index)
                    continue

                identifier = cleaned_asset_name
                jira_id = find_asset_in_jira(cleaned_asset_name)

                print(f"Processing: {asset_name} (Asset Name: {identifier})")

                if not jira_id:
                    print(f"   [SKIP] NOT FOUND IN JIRA: {asset_name} (update-only mode)")
                    log_skip(csv_path, asset_name, asset_id, identifier, "Not found in Jira by Asset Name (update-only mode)")
                    total_not_found += 1
                else:
                    if update_asset_in_jira(jira_id, asset):
                        total_updated += 1
                    else:
                        total_failed += 1

                current_progress = total_updated + total_not_found + total_failed + total_skipped
                print(f"[PROGRESS] Progress: {current_progress} processed so far.\n")

                asset_index += 1
                if asset_index % STATE_SAVE_EVERY == 0:
                    save_resume_state(asset_index)
                time.sleep(0.8)

            # Persist state at the end of each page.
            save_resume_state(asset_index)
            page += 1

    status_line = "[STATUS] Completed run"
    if run_aborted_reason:
        status_line = f"[STATUS] Aborted run: {run_aborted_reason}"

    report = f"""
==================================================
UPDATE-ONLY MIGRATION COMPLETE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
==================================================
[RUN] {status_line}
[SYNC] Total Updated in Jira:          {total_updated}
[SKIP] Not Found in Jira (No Create):  {total_not_found}
[WARN] Total Skipped (No Identifier):  {total_skipped}
[FAIL] Total Failed Updates:           {total_failed}
==================================================
"""

    print(report)

    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(log_dir, LOG_FILENAME)

    with open(log_path, mode="a", encoding="utf-8") as log_file:
        log_file.write(report + "\n")

    print(f"[REPORT] Report saved to: {log_path}")


if __name__ == "__main__":
    sync_assets_update_only()
