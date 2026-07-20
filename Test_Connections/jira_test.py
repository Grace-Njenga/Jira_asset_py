import requests
import os

from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

print(">>> DEBUG:", os.getenv("jira_url"))

JIRA_URL = os.getenv("Jira_url")
JIRA_EMAIL = os.getenv("Jira_Eml")
JIRA_API_TOKEN = os.getenv("Jira_Token")
WORKSPACE_ID = os.getenv("Wkspace_ID")  # JSM Assets workspace ID # JSM Assets workspace ID

HEADERS = {"Accept": "application/json"}
AUTH = (JIRA_EMAIL, JIRA_API_TOKEN)


def run_request(url):
    try:
        response = requests.get(url, auth=AUTH, headers=HEADERS)
        return response.status_code, response.text
    except Exception as exc:
        return None, str(exc)


def test_myself():
    url = f"{JIRA_URL.rstrip('/')}/rest/api/3/myself"
    status, text = run_request(url)
    print("--- Basic Jira auth test ---")
    print("URL:", url)
    print("Status:", status)
    print("Response:", text)
    print()
    return status


def test_workspace():
    url = f"{JIRA_URL.rstrip('/')}/gateway/api/jsm/assets/workspace/{WORKSPACE_ID}/v1/objectschema/list"
    status, text = run_request(url)
    print("--- JSM Assets workspace test ---")
    print("URL:", url)
    print("Status:", status)
    print("Response:", text)
    print()
    return status


if __name__ == "__main__":
    print("Using Jira URL:", JIRA_URL)
    print("Using Jira email:", JIRA_EMAIL)
    print("Using workspace ID:", WORKSPACE_ID)
    print()

    self_status = test_myself()
    if self_status == 200:
        print("Basic auth succeeded.")
    else:
        print("Basic auth failed. Fix the Jira email/token/site first.")

    workspace_status = test_workspace()
    if workspace_status == 200:
        print("Workspace access succeeded.")
    else:
        print("Workspace access failed. Check workspace ID and workspace permissions.")

