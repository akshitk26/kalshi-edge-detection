#!/usr/bin/env python3
"""Debug script to check raw API prices."""
import sys
sys.path.insert(0, '/Users/akshit/Code/kalshi-edge-detection')

import requests
import yaml

with open('edge_engine/config.yaml') as f:
    config = yaml.safe_load(f)

base_url = config['kalshi']['base_url']
email = config['kalshi']['email']
password = config['kalshi']['password']

# Login to get token
auth_resp = requests.post(
    f"{base_url}/login",
    json={'email': email, 'password': password}
)
print(f"Auth status: {auth_resp.status_code}")
if auth_resp.status_code != 200:
    print(f"Auth error: {auth_resp.text[:200]}")
    exit(1)
token = auth_resp.json().get('token')

# Fetch markets
headers = {'Authorization': f'Bearer {token}'}
resp = requests.get(
    f'{base_url}/markets',
    params={'series_ticker': 'KXHIGHNY', 'limit': 20},
    headers=headers
)
data = resp.json()

# Show all price fields for today's markets
print('Market                    | yes_bid | yes_ask | last  | volume')
print('-' * 65)
for m in data.get('markets', []):
    ticker = m.get('ticker', '')
    if 'FEB08' in ticker:
        bid = m.get('yes_bid', '-')
        ask = m.get('yes_ask', '-')
        last = m.get('last_price', '-')
        vol = m.get('volume', 0)
        print(f"{ticker:25} | {str(bid):7} | {str(ask):7} | {str(last):5} | {vol}")
