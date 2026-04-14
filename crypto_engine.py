import os
import requests
import feedparser
import time
import json
import re
import html
import sqlite3
import random
from io import BytesIO
from urllib.parse import quote
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from PIL import Image

# ==========================================
# 1. YOUR CONFIGURATION
# ==========================================
WP_URL = "https://blockcynic.com/index.php/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://blockcynic.com/index.php/wp-json/wp/v2/media"
WP_TAGS_URL = "https://blockcynic.com/index.php/wp-json/wp/v2/tags"

WP_USER = "adminipds"
WP_APP_PASSWORD = "9ppq BZkt 5wbj mEXf 7azk EPlM" 
WP_AUTHOR_ID = 3

# Environment Variables for Security
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "PASTE_FALLBACK_IF_NOT_IN_ENV")
JSON_KEY_FILE = "service_account.json" 

# Coolify Persistent Path logic
DB_PATH = "/app/data/" if os.path.exists("/app/data/") else ""
DB_FILE = f"{DB_PATH}crypto_processed.db"

client = genai.Client(api_key=GEMINI_API_KEY)

FALLBACK_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash-latest",
    "gemini-3.1-flash-lite-preview"
]

WP_CATEGORIES = {
    2: "Bitcoin & Ethereum",
    3: "Altcoins & Tokens",
    4: "Web3 & AI",
    5: "Market Analysis",
    6: "Regulation & Policy"
}

# ==========================================
# 2. TICKER & DATA FUNCTIONS
# ==========================================

def fetch_whale_movements():
    # Placeholder for Whale Alert API or manual tracking
    return "🐋 Whale Alert: Significant BTC movement detected on-chain | "

def fetch_market_sentiment():
    try:
        res = requests.get("https://api.alternative.me/fng/", timeout=10).json()
        val = res['data'][0]['value']
        classify = res['data'][0]['value_classification']
        return f"📊 Market Mood: {classify} ({val}/100) | "
    except:
        return "📊 Market Mood: Neutral | "

def fetch_live_prices():
    """Fetches Top 5 coins for the ticker."""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": "bitcoin,ethereum,solana,binancecoin,ripple",
            "price_change_percentage": "24h"
        }
        data = requests.get(url, params=params, timeout=10).json()
        
        price_segments = []
        for coin in data:
            sym = coin['symbol'].upper()
            price = f"${coin['current_price']:,}"
            change = coin['price_change_percentage_24h']
            arrow = "▲" if change > 0 else "▼"
            # Format with simple tags for the CSS to pick up
            price_segments.append(f"{sym} {price} {arrow} {abs(change):.2f}%")
            
        return " | ".join(price_segments) + " | "
    except:
        return ""

def update_live_ticker():
    # Gather everything
    prices = fetch_live_prices()
    sentiment = fetch_market_sentiment()
    whales = fetch_whale_movements()
    
    # Combined String
    ticker_text = f"{prices}{sentiment} || {whales}"
    
    # PUSH TO WP (Ensure this matches your REST API endpoint)
    payload = {"ticker_text": ticker_text}
    requests.post("https://blockcynic.com/wp-json/blockcynic/v1/update-ticker", 
                  auth=(WP_USER, WP_APP_PASSWORD), 
                  json=payload)
        

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
        res = requests.get(f"{WP_URL}?per_page=20&_fields=title", auth=(WP_USER, WP_APP_PASSWORD), timeout=15)
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
    return ", ".join(all_trends[:5]) if all_trends else "crypto markets, btc price, web3"

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
# 4. FEEDS & AGGREGATOR
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
    
    live_trends = get_live_trends()
    recent_posts = get_recent_posts_for_linking()
    update_live_ticker() # Refreshes ticker data

    for feed_info in FEEDS:
        print(f"\n--- Checking: {feed_info['name']} ---")
        try:
            feed = feedparser.parse(feed_info['url'])
            if not feed.entries: continue
            
            latest = feed.entries[0]
            original_title = latest.title
            article_link = latest.link

            # Image Gatekeeper
            image_url = None
            if 'media_content' in latest and latest.media_content:
                image_url = latest.media_content[0].get('url')
            elif 'links' in latest:
                for link in latest.links:
                    if 'image' in link.get('type', ''): image_url = link.href
            
            if not image_url:
                print(f"  [!] Gatekeeper: No image. Skipping.")
                continue

            if article_exists_in_wp(original_title, article_link):
                print(f"  [✓] Skipping: Already published.")
                continue

            # Standardize summary for AI
            raw_summary = getattr(latest, 'summary', original_title)
            article_summary = html.unescape(re.sub('<[^<]+?>', '', raw_summary))

            prompt = f"""
            You are a cynical, veteran quantitative crypto analyst for BlockCynic.com.
            News: {original_title}. Summary: {article_summary}.
            Trends: {live_trends}. Recent posts: {recent_posts}.
            
            Write a sharp, technical report (300 words).
            Format with <h2> tags: Catalyst, On-Chain Reality, Bull & Bear Case.
            Return ONLY valid JSON. 
            
            {{
              "title": "Cynical headline",
              "article_html": "HTML starting with TOC links",
              "meta_description": "150-char SEO snippet",
              "alt_text": "10-word descriptive alt text",
              "tags": ["Token", "Exchange", "Figure"],
              "category_ids": {feed_info['category_ids']},
              "focus_keyword": "2-word keyword"
            }}
            """

            ai_data = None
            for model_name in FALLBACK_MODELS:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    raw_text = re.sub(r'^```json\s*|\s*```$', '', response.text.strip(), flags=re.MULTILINE)
                    ai_data = json.loads(raw_text)
                    break 
                except: continue 

            if ai_data:
                media_id = upload_optimized_image_to_wp(image_url, original_title, ai_data['alt_text'])
                tag_ids = get_or_create_tags(ai_data['tags'])
                
                payload = {
                    "title": ai_data['title'],
                    "content": ai_data['article_html'],
                    "excerpt": ai_data['meta_description'],
                    "status": "publish",
                    "author": WP_AUTHOR_ID,
                    "categories": ai_data['category_ids'],
                    "tags": tag_ids,
                    "meta": {
                        "rank_math_focus_keyword": ai_data['focus_keyword'],
                        "rank_math_description": ai_data['meta_description']
                    }
                }
                if media_id: payload['featured_media'] = media_id

                wp_res = requests.post(WP_URL, auth=(WP_USER, WP_APP_PASSWORD), json=payload, timeout=20)
                if wp_res.status_code == 201:
                    print(f"  [+] Success! Article Live: {wp_res.json().get('link')}")
                    mark_url_processed(article_link)
                else: print(f"  [!] WP Error: {wp_res.status_code}")

        except Exception as e:
            print(f"  [!] Error processing {feed_info['name']}: {e}")

        time.sleep(10)

if __name__ == "__main__":
    while True:
        run_aggregator()
        print("\nSweep Complete. Sleeping for 2 hours...")
        time.sleep(7200)