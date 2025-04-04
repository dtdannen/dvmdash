#!/usr/bin/env python3
"""
Test script for the updated API endpoints that filter out inactive DVMs and kinds.
This script calls the API endpoints with different time ranges and prints the results.
"""

import requests
import json
from datetime import datetime

# API base URL
API_BASE = "http://localhost:8000"

def print_json(data):
    """Pretty print JSON data"""
    print(json.dumps(data, indent=2))

def test_dvm_list_endpoint():
    """Test the /api/dvms endpoint with different time ranges"""
    print("\n=== Testing /api/dvms endpoint ===")
    
    time_ranges = ["1h", "24h", "7d", "30d"]
    
    for time_range in time_ranges:
        print(f"\nTime range: {time_range}")
        response = requests.get(f"{API_BASE}/api/dvms?timeRange={time_range}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Total DVMs returned: {len(data['dvms'])}")
            
            # Print first few DVMs if available
            if data['dvms']:
                print("Sample DVMs:")
                for dvm in data['dvms'][:3]:  # Show first 3 DVMs
                    print(f"  - {dvm.get('dvm_name') or dvm['id']}: {dvm.get('total_responses', 0)} responses")
            else:
                print("No DVMs returned for this time range")
        else:
            print(f"Error: {response.status_code} - {response.text}")

def test_kind_list_endpoint():
    """Test the /api/kinds endpoint with different time ranges"""
    print("\n=== Testing /api/kinds endpoint ===")
    
    time_ranges = ["1h", "24h", "7d", "30d"]
    
    for time_range in time_ranges:
        print(f"\nTime range: {time_range}")
        response = requests.get(f"{API_BASE}/api/kinds?timeRange={time_range}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Total kinds returned: {len(data['kinds'])}")
            
            # Print first few kinds if available
            if data['kinds']:
                print("Sample kinds:")
                for kind in data['kinds'][:3]:  # Show first 3 kinds
                    print(f"  - Kind {kind['kind']}: {kind.get('total_requests', 0)} requests, {kind.get('total_responses', 0)} responses")
            else:
                print("No kinds returned for this time range")
        else:
            print(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print(f"Testing API at {API_BASE} at {datetime.now()}")
    
    test_dvm_list_endpoint()
    test_kind_list_endpoint()
    
    print("\nTests completed.")
