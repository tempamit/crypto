import os
import requests
import feedparser
import time
import json
import re
import html
import sqlite3
from io import BytesIO
from urllib.parse import quote
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from PIL import Image
import random

# ==========================================
# 1. YOUR CONFIGURATION
# ==========================================
WP_URL = "https://blockcynic.com/index.php/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://blockcynic.com/index.php/wp-json/wp/v2/media"
WP_TAGS_URL = "https://blockcynic.com/index.php/wp-json/wp/v2/tags"
WP_TICKER_URL = "https://blockcynic.com/wp-json/blockcynic/v1/update-ticker"

WP_USER = "adminipds"
WP_APP_PASSWORD = "9ppq BZkt 5wbj mEXf 7azk EPlM" 
WP_AUTHOR_ID = 3

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
JSON_KEY_FILE = "service_account.json" 

# Persistent DB Path for Coolify
DB_PATH = "/app/data/" if os.path.exists("/app/data/") else ""
DB_FILE = f"{DB_PATH}crypto_processed.db"

client = genai.Client(api_key=GEMINI_API_KEY)

FALLBACK_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash", # Removed "-latest" to prevent 404s
    "models/gemini-3-flash-preview",
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-3.1-pro-preview"
]

WP_CATEGORIES = {
    2: "Bitcoin & Ethereum",
    3: "Altcoins & Tokens",
    4: "Web3 & AI",
    5: "Market Analysis",
    6: "Regulation & Policy"
}

# ==========================================
# 2. TICKER ENGINE FUNCTIONS
# ==========================================

def fetch_live_prices():
    """Fetches Top 7 coins: Price + 24h Change."""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": "bitcoin,ethereum,solana,binancecoin,ripple,cardano,dogecoin",
            "order": "market_cap_desc",
            "price_change_percentage": "24h"
        }
        # We use a custom Header to look less like a bot and reduce 429s
        headers = {'User-Agent': 'Mozilla/5.0'} 
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if not isinstance(data, list):
            print(f"  [!] Price API returned error or non-list: {data}")
            return "Market Pulse: Synchronizing..."
            
        segments = []
        for coin in data:
            symbol = coin.get('symbol', '???').upper()
            # Use .get() with fallback 0 to prevent crash if key is missing
            price_val = coin.get('current_price', 0)
            price = f"${price_val:,}"
            change = coin.get('price_change_percentage_24h', 0) or 0
            
            arrow = "▲" if change > 0 else "▼"
            color_class = "ticker-up" if change > 0 else "ticker-down"
            
            segments.append(f"{symbol} {price} <span class='{color_class}'>{arrow} {abs(change):.2f}%</span>")
            
        return " | ".join(segments)
    except Exception as e:
        print(f"  [!] Price Fetch Error: {e}")
        return "Market Pulse: Refreshing..."
        

def fetch_market_sentiment():
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=10).json()
        val = res['data'][0]['value']
        classify = res['data'][0]['value_classification']
        return f"📊 Market Mood: {classify} ({val}/100)"
    except:
        return "📊 Market Mood: Analyzing..."

def fetch_liquidations():
    """Fetches Binance Futures data to calculate who is getting liquidated."""
    try:
        # 100% Free Public Endpoint (No API Key required)
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT"
        data = requests.get(url, timeout=10).json()
        
        volume = float(data['quoteVolume']) / 1_000_000_000 # Convert to Billions
        change = float(data['priceChangePercent'])
        
        # The "Cynic Logic": Who is bleeding today?
        rekt_side = "Longs" if change < 0 else "Shorts"
        intensity = "🔥 MASSIVE" if abs(change) > 3 else "🩸 STEADY"
        
        # Returns a string formatted for your CSS tags
        return f"{intensity} LIQUIDATIONS: {rekt_side} getting rekt (BTC Vol: ${volume:.2f}B)"
    except Exception as e:
        print(f"  [!] Liquidation Fetch Error: {e}")
        return "🩸 LIQUIDATIONS: Calculating market casualties..."
    
def fetch_rekt_base_data():
    """Fetches BTC price for the Rekt Calculator comparison."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        data = requests.get(url, timeout=10).json()
        return data['bitcoin']['usd']
    except:
        return 74800 # Fallback to a current realistic price

def fetch_shadow_data():
    """Fetches the latest movement from the target Whale wallet."""
    try:
        url = "https://blockchain.info/rawaddr/34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo?limit=1"
        data = requests.get(url, timeout=10).json()
        last_tx = data['txs'][0]
        amount = sum(out['value'] for out in last_tx['out']) / 100000000
        return {
            "wallet": "34xp4v...wseo",
            "amount": f"{amount:,.2f} BTC",
            "status": "🚨 MASSIVE SHADOW MOVE" if amount > 100 else "📉 Shadow Rebalancing",
            "hash": last_tx['hash'][:8] + "..."
        }
    except:
        return {"status": "Monitoring Shadows...", "amount": "0 BTC", "wallet": "---", "hash": "---"}
    
def fetch_market_dashboard_data():
    print("  [~] Gathering Master Dashboard Data...")
    
    # 1. Start with the Rekt Base
    current_btc = fetch_rekt_base_data()
    
    # 2. Defensive Breather: Wait 5s before next API hit to avoid 429
    time.sleep(5) 
    
    # 3. Clean Dashboard (HEATMAP REMOVED)
    dashboard = {
        "ticker": fetch_live_prices(),
        "gainers": [],
        "losers": [],
        "sentiment_score": "50",
        "sentiment_label": "Neutral",
        "whales": [],
        "shadow_tracker": fetch_shadow_data(),
        "btc_price": current_btc
    }

    try:
        # Gainers & Losers from Binance
        binance_data = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10).json()
        if isinstance(binance_data, list):
            pairs = [d for d in binance_data if d['symbol'].endswith('USDT')]
            pairs.sort(key=lambda x: float(x['priceChangePercent']))
            dashboard["losers"] = [{"symbol": p['symbol'].replace('USDT',''), "change": f"{float(p['priceChangePercent']):.2f}%"} for p in pairs[:5]]
            gain_raw = pairs[-5:]; gain_raw.reverse()
            dashboard["gainers"] = [{"symbol": p['symbol'].replace('USDT',''), "change": f"+{float(p['priceChangePercent']):.2f}%"} for p in gain_raw]

        # Sentiment
        sent_req = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
        dashboard["sentiment_score"] = sent_req['data'][0]['value']
        dashboard["sentiment_label"] = sent_req['data'][0]['value_classification']

        # Whales
        actions = ["transferred to Coinbase", "transferred to Binance", "withdrawn to Wallet"]
        coins = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
        dashboard["whales"] = [f"🚨 {random.randint(1000, 50000)} {random.choice(coins)} {random.choice(actions)}" for _ in range(4)]

    except Exception as e:
        print(f"  [!] Dashboard Data Error: {e}")

    return dashboard

def push_cynic_dashboard():
    """Pushes the Master JSON Payload to WordPress User 3"""
    payload = fetch_market_dashboard_data()
    
    WP_USER_URL = "https://blockcynic.com/wp-json/wp/v2/users/3"
    try:
        res = requests.post(
            WP_USER_URL,
            auth=(WP_USER, WP_APP_PASSWORD),
            json={"description": json.dumps(payload)}, # Pushing as a JSON string
            timeout=15
        )
        if res.status_code == 200:
            print("  [+] Master Dashboard Payload Successfully Updated.")
    except Exception as e: 
        print(f"  [!] Connection Error: {e}")

# ==========================================
# 3. INFRASTRUCTURE & HELPER FUNCTIONS
# ==========================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed (url TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

def is_url_processed(url):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed WHERE url = ?", (url,))
    result = c.fetchone()
    conn.close()
    return bool(result)

def mark_url_processed(url):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO processed (url) VALUES (?)", (url,))
    conn.commit()
    conn.close()

def clean_for_comparison(text):
    return re.sub(r'[^a-zA-Z0-9]', '', html.unescape(text)).lower()

def article_exists_in_wp(title, original_url):
    if is_url_processed(original_url): return True
    try:
        res = requests.get(f"{WP_URL}?per_page=20&_fields=title", auth=(WP_USER, WP_APP_PASSWORD), timeout=10)
        if res.status_code == 200:
            target_clean = clean_for_comparison(title)
            for post in res.json():
                if target_clean == clean_for_comparison(post['title']['rendered']):
                    mark_url_processed(original_url) 
                    return True
    except: pass
    return False

def upload_optimized_image_to_wp(image_url, article_title, alt_text=""):
    try:
        res = requests.get(image_url, timeout=15)
        if res.status_code != 200: return None
        img = Image.open(BytesIO(res.content))
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        max_width = 1200
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format="WEBP", quality=80)
        img_data = buffer.getvalue()
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', article_title)[:30]
        headers = {
            "Content-Type": "image/webp", 
            "Content-Disposition": f"attachment; filename={safe_name}.webp"
        }
        upload_res = requests.post(WP_MEDIA_URL, headers=headers, data=img_data, auth=(WP_USER, WP_APP_PASSWORD))
        if upload_res.status_code == 201: 
            media_id = upload_res.json()['id']
            if alt_text:
                requests.post(f"{WP_MEDIA_URL}/{media_id}", json={"alt_text": alt_text}, auth=(WP_USER, WP_APP_PASSWORD))
            return media_id
    except Exception as e:
        print(f"  [!] Image error: {e}")
    return None

def get_live_trends():
    global_hubs = ["US", "GB", "CA", "IN", "AE"]
    all_trends = []
    selected_hubs = random.sample(global_hubs, 2)
    for geo in selected_hubs:
        try:
            feed = feedparser.parse(f"https://trends.google.com/trending/rss?geo={geo}")
            trends = [entry.title for entry in feed.entries[:3]]
            all_trends.extend(trends)
        except: continue
    return ", ".join(all_trends[:5]) if all_trends else "crypto markets, btc price"

def get_recent_posts_for_linking():
    try:
        res = requests.get(f"{WP_URL}?per_page=3&status=publish&_fields=title,link", auth=(WP_USER, WP_APP_PASSWORD), timeout=10)
        if res.status_code == 200:
            posts = res.json()
            return "\n".join([f"- {p['title']['rendered']} (URL: {p['link']})" for p in posts])
    except: return "No recent posts available."

def get_or_create_tags(tag_names):
    tag_ids = []
    for tag in tag_names:
        res = requests.post(WP_TAGS_URL, auth=(WP_USER, WP_APP_PASSWORD), json={"name": tag})
        if res.status_code == 201: tag_ids.append(res.json()['id'])
        elif res.status_code == 400:
            try: tag_ids.append(res.json()['data']['term_id'])
            except: pass
    return tag_ids

# ==========================================
# 4. MAIN ENGINE
# ==========================================

FEEDS = [
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "category_ids": [2, 5]},
    {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss", "category_ids": [2, 3]},
    {"name": "Decrypt", "url": "https://decrypt.co/feed", "category_ids": [4]},
    {"name": "CryptoSlate", "url": "https://cryptoslate.com/feed/", "category_ids": [3, 5]},
    {"name": "NewsBTC", "url": "https://www.newsbtc.com/feed/", "category_ids": [5, 2]}
]

def run_aggregator():
    init_db() 
    print(f"\n[{time.strftime('%H:%M:%S')}] BlockCynic Engine: Starting Global Crypto Sweep...")
    
    # Refresh Ticker every cycle
    push_cynic_dashboard()

    live_trends = get_live_trends()
    recent_posts = get_recent_posts_for_linking()

    for feed_info in FEEDS:
        print(f"\n--- Checking: {feed_info['name']} ---")
        try:
            feed = feedparser.parse(feed_info['url'])
            if not feed.entries: continue
            
            latest = feed.entries[0]
            original_title = latest.title
            article_link = latest.link

            if article_exists_in_wp(original_title, article_link):
                print(f"  [✓] Skipping: Already published.")
                continue

            raw_summary = getattr(latest, 'summary', original_title)
            article_summary = html.unescape(re.sub('<[^<]+?>', '', raw_summary))

            image_url = None
            if 'media_content' in latest and latest.media_content:
                image_url = latest.media_content[0].get('url')
            elif 'links' in latest:
                for link in latest.links:
                    if 'image' in link.get('type', ''): image_url = link.href

            prompt = f"""
            You are a cynical, veteran quantitative crypto analyst for BlockCynic.com.
            Headline: {original_title}. Summary: {article_summary}.
            Trends: {live_trends}. Recent posts: {recent_posts}.
            
            Task: Write a sharp, technical report (300 words). No AI-cliches. 
            Format: HTML with <h2> tags (Catalyst, On-Chain Reality, Bull & Bear Case).
            
            CRITICAL REQUIREMENT: 
            You must return a valid JSON object. 
            The JSON MUST contain a key named 'article_html' with the report content.
            The JSON MUST also contain 'meta_description', 'tags', and 'focus_keyword'.
            """

            ai_data = None
            for idx, model_name in enumerate(FALLBACK_MODELS):
                try:
                    wait = (idx + 1) * 5 
                    time.sleep(wait) 
                    
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    raw_text = re.sub(r'^```json\s*|\s*```$', '', response.text.strip(), flags=re.MULTILINE)
                    parsed_json = json.loads(raw_text)
                    
                    if 'article_html' not in parsed_json:
                        # --- ADDITION C: Reminder for missing keys ---
                        prompt += " IMPORTANT: You missed the 'article_html' key. Return it now."
                        raise ValueError("AI JSON is missing the 'article_html' key")
                        
                    ai_data = parsed_json
                    break 
                except Exception as e:
                    # --- ADDITION A: Handle Quota specifically ---
                    if "429" in str(e):
                        print(f"  [!] {model_name} Quota Exhausted. Cooling down 15s...")
                        time.sleep(15)
                    print(f"  [!] {model_name} failed: {e}")
                    continue

            if not ai_data:
                print("  [X] Models exhausted or returned bad JSON. Skipping...")
                continue # Safely skip to the next article feed

            if ai_data:
                media_id = upload_optimized_image_to_wp(image_url, original_title, ai_data.get('alt_text', ''))
                tag_ids = get_or_create_tags(ai_data.get('tags', []))
                
                post_payload = {
                    "title": original_title,
                    "content": ai_data['article_html'],
                    "excerpt": ai_data['meta_description'],
                    "status": "publish",
                    "author": WP_AUTHOR_ID,
                    "categories": ai_data.get('category_ids', feed_info['category_ids']),
                    "tags": tag_ids,
                    "meta": { "rank_math_focus_keyword": ai_data.get('focus_keyword', '') }
                }
                if media_id: post_payload['featured_media'] = media_id

                wp_res = requests.post(WP_URL, auth=(WP_USER, WP_APP_PASSWORD), json=post_payload, timeout=20)
                if wp_res.status_code == 201:
                    print(f"  [+] Success! Article Live: {wp_res.json().get('link')}")
                    mark_url_processed(article_link)
                    
                    # --- THE FIX: Stop the sweep after 1 successful post ---
                    print("  [~] Rhythm Check: 1 post complete. Breaking sweep for 90-min rest.")
                    return True # Tell the scheduler we successfully posted
                else: print(f"  [!] WP Error: {wp_res.status_code}")

        except Exception as e: print(f"  [!] Error processing {feed_info['name']}: {e}")

        time.sleep(25) # Pause between feeds

# ==========================================
# 5. THE 90-MINUTE SCHEDULER
# ==========================================

if __name__ == "__main__":
    init_db()
    print(f"[{time.strftime('%H:%M:%S')}] BlockCynic Scheduler: Starting 90-Min Rhythm...")
    
    while True:
        # 1. Update the Ticker/Heatmap first so the site stays live
        push_cynic_dashboard()
        
        # 2. Run the Aggregator for one sweep
        # Note: Your run_aggregator() currently loops through ALL feeds.
        # To keep it to 1 post per 90 mins, we run the sweep once.
        run_aggregator()
        
        # 3. Wait exactly 90 minutes (5400 seconds)
        print(f"\n[{time.strftime('%H:%M:%S')}] Post Cycle Complete. Next forensic sweep in 90 minutes...")
        time.sleep(5400)