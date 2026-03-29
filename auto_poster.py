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
# 1. YOUR CONFIGURATION
# ==========================================
WP_URL = "https://news.ipds.cloud/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://news.ipds.cloud/wp-json/wp/v2/media"
WP_TAGS_URL = "https://news.ipds.cloud/wp-json/wp/v2/tags"

WP_USER = "adminipds"
WP_APP_PASSWORD = "Jjkr amue uHw0 tGDx OCKu iJYz" 

GEMINI_API_KEY = "AIzaSyCURIszps9ihHRA-CFap3xAHriZcJf2g6c"
JSON_KEY_FILE = "service_account.json" 
DB_FILE = "processed_urls.db" 

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
    1: "Uncategorized",
    2: "Movies",
    3: "Music",
    4: "Celebrities",
    5: "Lifestyle",
    6: "Global",
    7: "Bollywood",
    8: "Hollywood",
    56: "OTT",
    57: "Gaming",
    58: "Anime",
    59: "K-Pop",
    60: "Tech"
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
    {"name": "FilmiBeat Bollywood (India)", "url": "https://www.filmibeat.com/rss/feeds/bollywood-fb.xml", "category_ids": [7, 2]},
    {"name": "Times of India (Bollywood)", "url": "https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms", "category_ids": [7, 2]},
    # Regional Movies & General Indian Entertainment
    {"name": "News18 Movies", "url": "https://www.news18.com/rss/movies.xml", "category_ids": [2, 7]},
    {"name": "Indian Express Entertainment", "url": "https://indianexpress.com/section/entertainment/feed/", "category_ids": [2, 4]},
    #  {"name": "Variety Film (Hollywood)", "url": "https://variety.com/v/film/feed/", "category_ids": [8, 2]},
      # {"name": "BBC Entertainment (Global)", "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "category_ids": [6]},
    #  {"name": "NME (Global Music)", "url": "https://www.nme.com/news/music/feed", "category_ids": [3, 6]},
    {"name": "E! Online Top Stories (Lifestyle)", "url": "https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml", "category_ids": [4, 5]},
    {"name": "Hindustan Times (OTT & Web Series)", "url": "https://www.hindustantimes.com/feeds/rss/entertainment/web-series/rssfeed.xml", "category_ids": [56]},
     # {"name": "IGN (Global Gaming & Esports)", "url": "https://feeds.ign.com/ign/games-all", "category_ids": [57]},
     #  {"name": "Anime News Network (Anime & Manga)", "url": "https://www.animenewsnetwork.com/news/rss.xml", "category_ids": [58]},
    #  {"name": "Soompi (K-Pop & K-Drama)", "url": "https://www.soompi.com/feed", "category_ids": [59, 3]},
     #  {"name": "The Verge (Entertainment Tech)", "url": "https://www.theverge.com/rss/index.xml", "category_ids": [60]}
    # Television & Daily Soaps (Massive Indian Search Volume)
    {"name": "Times of India TV", "url": "https://timesofindia.indiatimes.com/rssfeeds/65289941.cms", "category_ids": [4, 56]}
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
            prompt = f"""
            You are an elite, highly opinionated industry analyst and senior journalist. Your job is not just to report the news, but to explain WHY it matters.
            Title: {original_title}
            Summary: {summary}
            
            ANTI-ROBOTIC & SEO INSTRUCTIONS:
            1. Information Gain (CRITICAL): Include a dedicated <h3> section titled "The Big Picture" or "Why It Matters" where you provide historical context, industry impact, or forward-looking analysis based on your knowledge of the topic.
            2. Humanize the text: Use high burstiness (mix very short, punchy sentences with longer, complex ones). AVOID cliché AI phrases entirely.
            3. Format: NEVER use <h1> tags. Use strictly <h2> and <h3> tags for hierarchy. Start the article_html with a quick bulleted Table of Contents with jump links.
            4. Entity Tagging (CRITICAL): Extract 3 to 5 highly specific Proper Nouns (Entities) from the article to use as tags. Examples: "Ranveer Singh", "PlayStation 5", "Federal Reserve", "Dhurandhar 2". DO NOT use generic tags like "Bollywood" or "Gaming".
            5. Internal Linking: Contextually hyperlink 1 or 2 of these recent articles directly inside your body paragraphs using natural anchor text:
               {recent_posts}
            6. Generate a valid NewsArticle JSON-LD Schema block wrapped in <script type="application/ld+json"> tags.
            7. Generate a 10-word, highly descriptive Alt Text for the featured image.
            8. Categorization: Review this list of my website categories: {WP_CATEGORIES}. Select the 1 or 2 most appropriate Category IDs.

            MANDATORY: Return ONLY a valid JSON object. Escape double quotes correctly.
            Structure:
            {{
              "article_html": "HTML post starting with TOC, followed by the news report, the analytical 'Why It Matters' section, internal links woven in, ending with the schema block",
              "meta_description": "150-char SEO snippet that teases the analysis, not just the facts",
              "alt_text": "10 word descriptive image alt text",
              "tags": ["Specific Person", "Specific Product/Movie", "Specific Organization"],
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