import requests
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("Testing Freshservice connection...")

try:
    # Test basic connectivity
    response = requests.get(
        'https://alliance.freshservice.com',
        verify=False,
        timeout=10
    )
    print(f"Basic connection: {response.status_code}")

    # Test API endpoint
    response = requests.get(
        'https://alliance.freshservice.com/api/v2/assets',
        auth=('DbbbetkOM_FKsb-5s7c8', 'X'),
        verify=False,
        timeout=15
    )
    print(f"API Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Found {len(data.get('assets', []))} assets on first page")
    else:
        print(f"API Error: {response.text[:200]}")

except Exception as e:
    print(f"Error: {e}")