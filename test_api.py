import requests
import json
import urllib.parse

# The relay URL we want to remove
relay_url = "wss://relay.vertexlab.io"

# The API base URL
api_base = "http://localhost:8000"  # Use localhost since we're running this on the host

# Test 1: Try with the new query parameter endpoint
test1_url = f"{api_base}/api/admin/relay?url={urllib.parse.quote(relay_url)}"
print(f"Test 1: DELETE {test1_url}")
response = requests.delete(test1_url)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
print()

# Test 5: Get all relays to see what's actually in the database
test5_url = f"{api_base}/api/admin/relays"
print(f"Test 5: GET {test5_url}")
response = requests.get(test5_url)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
print()

# Test 6: Get Redis debug info to see what's in Redis
test6_url = f"{api_base}/api/admin/debug/redis"
print(f"Test 6: GET {test6_url}")
response = requests.get(test6_url)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
print()
