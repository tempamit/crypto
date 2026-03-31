import os # Make sure this is at the top with your other imports
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

# ==========================================
# 1. YOUR CONFIGURATION #
# ==========================================
WP_URL = "https://crypto.ipds.cloud/index.php/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://crypto.ipds.cloud/index.php/wp-json/wp/v2/media"
WP_TAGS_URL = "https://crypto.ipds.cloud/index.php/wp-json/wp/v2/tags"

WP_USER = "adminipds"
WP_APP_PASSWORD = "IEtw OMiW Jtjp JzW1 CypZ 16UK" 

# --- CHANGED: Hide the API Key from GitHub ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

JSON_KEY_FILE = "service_account.json" 
DB_FILE = "crypto_processed.db" # CRITICAL: Renamed so it doesn't conflict

client = genai.Client(api_key=GEMINI_API_KEY)

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-pro-preview"
]

WP_CATEGORIES = {
    2: "Bitcoin & Ethereum",
    3: "Altcoins & Tokens",
    4: "Web3 & AI",
    5: "Market Analysis",
    6: "Regulation & Policy"
}

# ==========================================
# 2. INFRASTRUCTURE & HELPER FUNCTIONS
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
        res = requests.get(f"{WP_URL}?per_page=20&_fields=title", auth=(WP_USER, WP_APP_PASSWORD))
        if res.status_code == 200:
            target_clean = clean_for_comparison(title)
            for post in res.json():
                if target_clean == clean_for_comparison(post['title']['rendered']):
                    mark_url_processed(original_url) 
                    return True
    except: pass
    return False

def upload_optimized_image_to_wp(image_url, article_title, alt_text=""):
    """Upgraded: Converts to WebP AND injects SEO Alt Text."""
    try:
        res = requests.get(image_url, timeout=10)
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
            # SECONDARY API CALL: Inject the SEO Alt Text into the database
            if alt_text:
                requests.post(f"{WP_MEDIA_URL}/{media_id}", json={"alt_text": alt_text}, auth=(WP_USER, WP_APP_PASSWORD))
            return media_id
    except Exception as e:
        print(f"  [!] Image optimization error: {e}")
    return None

def get_live_trends():
    try:
        feed = feedparser.parse("https://trends.google.com/trending/rss?geo=IN")
        trends = [entry.title for entry in feed.entries[:5]]
        return ", ".join(trends) if trends else "latest updates, breaking news"
    except Exception:
        return "latest updates, breaking news, trending online"

def get_recent_posts_for_linking():
    """Fetches the 3 newest WP articles to feed to the AI for internal linking."""
    try:
        res = requests.get(f"{WP_URL}?per_page=3&status=publish&_fields=title,link", auth=(WP_USER, WP_APP_PASSWORD))
        if res.status_code == 200:
            posts = res.json()
            links_data = [f"- {p['title']['rendered']} (URL: {p['link']})" for p in posts]
            return "\n".join(links_data)
    except: pass
    return "No recent posts available."

def ping_google_indexing(url):
    try:
        scopes = ["https://www.googleapis.com/auth/indexing"]
        credentials = service_account.Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
        service = build("indexing", "v3", credentials=credentials)
        service.urlNotifications().publish(body={"url": url, "type": "URL_UPDATED"}).execute()
        print(f"  [+] Google Indexing API: Pinged {url}")
    except: pass

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
# 3. MAIN ENGINE
# ==========================================

FEEDS = [
    {"name": "CoinDesk (Markets)", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "category_ids": [2, 5]},
    {"name": "CoinTelegraph (Top News)", "url": "https://cointelegraph.com/rss", "category_ids": [2, 3]},
    {"name": "Decrypt (Web3 & AI)", "url": "https://decrypt.co/feed", "category_ids": [4]},
    {"name": "CryptoSlate (Altcoins)", "url": "https://cryptoslate.com/feed/", "category_ids": [3, 5]},
    {"name": "NewsBTC (Analysis)", "url": "https://www.newsbtc.com/feed/", "category_ids": [5, 2]}
]

def run_aggregator():
    init_db() 
    print("\nStarting Global SEO News Sweep...")
    
    live_trends = get_live_trends()
    recent_posts = get_recent_posts_for_linking() # Fetch internal links
    print(f"  [~] Live Trends Hooked: {live_trends}")

    for feed_info in FEEDS:
        print(f"\n--- Checking: {feed_info['name']} ---")
        try:
            feed = feedparser.parse(feed_info['url'])
            if not feed.entries: continue
            
            latest = feed.entries[0]
            original_title = latest.title
            article_link = latest.link

            if article_exists_in_wp(original_title, article_link):
                print(f"  [✓] Skipping: Already published ('{original_title[:30]}...')")
                continue

            summary = getattr(latest, 'summary', original_title)
            
            image_url = None
            if 'media_content' in latest: image_url = latest.media_content[0]['url']
            elif 'links' in latest:
                for link in latest.links:
                    if 'image' in link.get('type', ''): image_url = link.href

            # --- THE "INFORMATION GAIN" SEO PROMPT ---
            # --- THE "ENTITY HUB & INFORMATION GAIN" SEO PROMPT ---
            # --- THE CRYPTO QUANT ANALYST PROMPT ---
            prompt = f"""
            You are a cynical, veteran quantitative crypto analyst who has survived three bear markets. 
            You are reviewing this raw news feed. Write a sharp, highly technical, 300-word market update.
            
            News Title: {original_title}
            Raw Data: {summary}
            
            STRICT "HUMAN-TOUCH" INSTRUCTIONS (CRITICAL):
            1. Ban List: YOU MUST NEVER USE the following words or phrases: "delving into", "in conclusion", "ever-evolving", "a testament to", "crucial", "vital", "surprising turn of events", "navigating", "landscape".
            2. Tone: Write like a Wall Street trader speaking to other traders. Use high burstiness (very short, punchy sentences mixed with data-heavy analysis). Be direct. No fluff. 
            
            ALGORITHMIC RESEARCH & EXPERT EDGE:
            Divide the article_html into these exact sections using strictly <h2> tags (NEVER use <h1>):
            - <h2>The Catalyst</h2>: State exactly what happened in 2-3 sentences. No filler.
            - <h2>The On-Chain Reality</h2>: Synthesize this news. What is the actual macro-economic or technical impact? (e.g., liquidity, support/resistance, network hash rates, ETF flows).
            - <h2>The Bull & Bear Case</h2>: Use a <ul> bulleted list to give one reason this is bullish (The Long Play), and one reason it is a trap (The Short Risk).
            
            3. Keyword & Link Injection: Weave these live trends naturally: {live_trends}. Contextually hyperlink 1 or 2 of these recent articles using natural anchor text:
               {recent_posts}
            4. Start the article_html with a quick bulleted Table of Contents with jump links to the 3 H2 sections.
            5. Generate a valid NewsArticle JSON-LD Schema block wrapped in <script type="application/ld+json">.
            6. Generate a 10-word, highly descriptive Alt Text for the featured image (focus on charts, tokens, or executives).
            7. Categorization: Review this list of my website categories: {WP_CATEGORIES}. Select the 1 or 2 most appropriate Category IDs.

            MANDATORY: Return ONLY a valid JSON object. Escape double quotes correctly.
            Structure:
            {{
              "article_html": "HTML post starting with TOC, followed by the 3 H2 sections, ending with the schema block",
              "meta_description": "150-char SEO snippet focused on market impact and price action",
              "alt_text": "10 word descriptive image alt text",
              "tags": ["Exact Token Name", "Specific Exchange", "Key Figure"],
              "category_ids": [integer_id1, integer_id2]
            }}
            """
            
            ai_data = None
            for model_name in FALLBACK_MODELS:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    raw_text = response.text.strip()
                    raw_text = re.sub(r'^```json\s*|\s*```$', '', raw_text, flags=re.MULTILINE)
                    ai_data = json.loads(raw_text)
                    break 
                except Exception as e:
                    print(f"  [!] Error with {model_name}: {e}. Trying next...")
                    continue 

            if not ai_data:
                print("  [X] Models exhausted. Cooling down...")
                time.sleep(60)
                continue 

            chosen_categories = ai_data.get('category_ids', feed_info.get('category_ids', [2]))
            print(f"  [~] AI assigned categories: {chosen_categories}")

            final_content = ai_data['article_html'] 
            
            # Extract Alt Text and pass it to the Image Optimizer
            alt_text = ai_data.get('alt_text', original_title)
            media_id = upload_optimized_image_to_wp(image_url, original_title, alt_text) if image_url else None
            
            tag_ids = get_or_create_tags(ai_data.get('tags', []))

            # --- UPDATED NATIVE SEO PAYLOAD ---
            seo_description = ai_data.get('meta_description', '')
            
            post_payload = {
                "title": original_title,
                "content": final_content,
                "excerpt": seo_description, # Standard WP Fallback
                "status": "publish",
                "categories": chosen_categories,
                "tags": tag_ids,
                "_yoast_wpseo_metadesc": seo_description, # Injects directly into Yoast
                "rank_math_description": seo_description  # Injects directly into Rank Math
            }
            if media_id: post_payload['featured_media'] = media_id

            wp_res = requests.post(WP_URL, auth=(WP_USER, WP_APP_PASSWORD), json=post_payload)
            
            if wp_res.status_code == 201:
                new_url = wp_res.json().get('link')
                print(f"  [+] Success! Article Live: {new_url}")
                mark_url_processed(article_link) 
                ping_google_indexing(new_url)
            else:
                print(f"  [!] WordPress Error: {wp_res.status_code}")

        except Exception as e:
            print(f"General Error processing {feed_info['name']}: {e}")

        time.sleep(300)

if __name__ == "__main__":
    while True:
        run_aggregator()
        print("\nSweep Complete. Sleeping for 2 hours...")
        time.sleep(7200)