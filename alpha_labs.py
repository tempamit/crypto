import requests
import json
import time

# --- CONFIGURATION ---
# Example: A known high-value Whale Wallet
SHADOW_WALLET = "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo" 
WP_USER_URL = "https://blockcynic.com/wp-json/wp/v2/users/3"
WP_USER = "adminipds"
WP_APP_PASSWORD = "9ppq BZkt 5wbj mEXf 7azk EPlM" 

def fetch_shadow_movement():
    print(f"[~] Monitoring Shadow Wallet: {SHADOW_WALLET[:10]}...")
    try:
        url = f"https://blockchain.info/rawaddr/{SHADOW_WALLET}?limit=1"
        data = requests.get(url, timeout=10).json()
        
        last_tx = data['txs'][0]
        tx_hash = last_tx['hash']
        # Convert satoshis to BTC
        amount = sum(out['value'] for out in last_tx['out']) / 100000000
        
        # We only care if it's a "Heavy" move (e.g., > 100 BTC)
        if amount > 100:
            status = "🚨 MASSIVE SHADOW MOVE DETECTED"
        else:
            status = "📉 Minor Shadow Rebalancing"
            
        return {
            "wallet": SHADOW_WALLET[:6] + "..." + SHADOW_WALLET[-4:],
            "amount": f"{amount:,.2f} BTC",
            "status": status,
            "hash": tx_hash[:8] + "..."
        }
    except Exception as e:
        print(f"[!] Error fetching wallet data: {e}")
        return None

def update_alpha_payload():
    movement = fetch_shadow_movement()
    if not movement: return

    # We fetch the existing Master JSON so we don't overwrite the ticker/bento
    try:
        current_profile = requests.get(WP_USER_URL).json()
        master_data = json.loads(current_profile['description'])
    except:
        master_data = {}

    # Add the new Shadow Tracker data to the Master JSON
    master_data['shadow_tracker'] = movement

    # Push back to WordPress
    res = requests.post(
        WP_USER_URL,
        auth=(WP_USER, WP_APP_PASSWORD),
        json={"description": json.dumps(master_data)},
        timeout=15
    )
    if res.status_code == 200:
        print("[+] Alpha Labs: Shadow Tracker Updated.")

if __name__ == "__main__":
    update_alpha_payload()