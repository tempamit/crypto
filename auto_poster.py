import requests
import feedparser
import time
import json
import re
import html
from urllib.parse import quote
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pytrends.request import TrendReq

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

client = genai.Client(api_key=GEMINI_API_KEY)

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash"
]

# SESSION MEMORY: Prevents rapid-fire duplicates if WP cache is slow
SESSION_PROCESSED_URLS = set()

# ==========================================
# 2. ADVANCED HELPER FUNCTIONS
# ==========================================

def clean_for_comparison(text):
    """Strips all punctuation, spaces, and special chars for a strict raw-text match."""
    return re.sub(r'[^a-zA-Z0-9]', '', html.unescape(text)).lower()

def article_exists_in_wp(title, original_url):
    """Bulletproof duplicate checker using alphanumeric matching."""
    if original_url in SESSION_PROCESSED_URLS:
        return True # We literally just posted this
        
    try:
        # Fetch the latest 20 posts to check against, avoiding WP's fuzzy search
        res = requests.get(f"{WP_URL}?per_page=20&_fields=title", auth=(WP_USER, WP_APP_PASSWORD))
        if res.status_code == 200:
            posts = res.json()
            target_clean = clean_for_comparison(title)
            
            for post in posts:
                wp_clean = clean_for_comparison(post['title']['rendered'])
                if target_clean == wp_clean:
                    return True
    except Exception as e:
        print(f"  [!] Duplicate check error: {e}")
    return False

def get_live_trends():
    """Fetches real-time Google Trends for India using the official RSS feed."""
    try:
        # Official Google Trends RSS for India
        trends_url = "https://trends.google.com/trending/rss?geo=IN"
        feed = feedparser.parse(trends_url)
        
        trends = []
        # Grab the top 5 trending keywords
        for entry in feed.entries[:5]:
            trends.append(entry.title)
            
        if trends:
            return ", ".join(trends)
        else:
            raise Exception("Empty trends feed")
    except Exception as e:
        print(f"  [!] Trends RSS warning: {e}. Using static LSI keywords.")
        return "latest updates, breaking news, trending online, exclusive details, viral story"
        
def ping_google_indexing(url):
    try:
        scopes = ["https://www.googleapis.com/auth/indexing"]
        credentials = service_account.Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
        service = build("indexing", "v3", credentials=credentials)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        print(f"  [+] Google Indexing API: Pung {url}")
    except Exception as e:
        pass

def get_related_posts_html(category_id):
    try:
        params = {"categories": category_id, "per_page": 3, "status": "publish"}
        res = requests.get(WP_URL, params=params)
        if res.status_code == 200 and res.json():
            html_out = "<br><hr><h3>Related News You Might Like:</h3><ul>"
            for p in res.json():
                html_out += f'<li><a href="{p["link"]}">{p["title"]["rendered"]}</a></li>'
            return html_out + "</ul>"
    except: pass
    return ""

def upload_image_to_wp(image_url, article_title):
    try:
        img_data = requests.get(image_url, timeout=10).content
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', article_title)[:30]
        headers = {"Content-Type": "image/jpeg", "Content-Disposition": f"attachment; filename={safe_name}.jpg"}
        res = requests.post(WP_MEDIA_URL, headers=headers, data=img_data, auth=(WP_USER, WP_APP_PASSWORD))
        if res.status_code == 201: return res.json()['id']
    except: pass
    return None

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
    {"name": "Variety Film (Hollywood)", "url": "https://variety.com/v/film/feed/", "category_ids": [8, 2]}
    # Add your other feeds back here...
]

def run_aggregator():
    print("\nStarting Global SEO News Sweep...")
    
    # 1. Fetch live trends for this cycle
    live_trends = get_live_trends()
    print(f"  [~] Live Trends Hooked: {live_trends}")

    for feed_info in FEEDS:
        print(f"\n--- Checking: {feed_info['name']} ---")
        try:
            feed = feedparser.parse(feed_info['url'])
            if not feed.entries: continue
            
            latest = feed.entries[0]
            original_title = latest.title
            article_link = latest.link

            # --- THE NEW DUPLICATE CHECKER ---
            if article_exists_in_wp(original_title, article_link):
                print(f"  [✓] Skipping: Already published ('{original_title[:30]}...')")
                continue

            summary = getattr(latest, 'summary', original_title)
            
            # Find Image
            image_url = None
            if 'media_content' in latest: image_url = latest.media_content[0]['url']
            elif 'links' in latest:
                for link in latest.links:
                    if 'image' in link.get('type', ''): image_url = link.href

            # --- ADVANCED SEO PROMPT ---
            prompt = f"""
            You are an elite SEO viral news writer. Rewrite this news into a highly engaging, 300-word conversational post. 
            Title: {original_title}
            Summary: {summary}
            
            SEO Instructions:
            1. Naturally weave some of these trending keywords into the text if relevant: {live_trends}.
            2. Start the article_html with a quick bulleted Table of Contents with jump links (e.g., <a href="#section1">).
            3. Use <h2> tags with matching IDs (e.g., <h2 id="section1">) to divide the content.
            4. Generate a valid NewsArticle JSON-LD Schema block wrapped in <script type="application/ld+json"> tags.

            MANDATORY: Return ONLY a valid JSON object. Escape double quotes correctly.
            Structure:
            {{
              "article_html": "HTML post starting with TOC, followed by content, ending with the schema <script> block",
              "meta_description": "150-char SEO snippet",
              "tags": ["trending_keyword1", "trending_keyword2"]
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

            # Build Final Content
            related_html = get_related_posts_html(feed_info['category_ids'][0])
            final_content = ai_data['article_html'] + related_html

            media_id = upload_image_to_wp(image_url, original_title) if image_url else None
            tag_ids = get_or_create_tags(ai_data['tags'])

            post_payload = {
                "title": original_title,
                "content": final_content,
                "excerpt": ai_data['meta_description'],
                "status": "publish",
                "categories": feed_info['category_ids'],
                "tags": tag_ids
            }
            if media_id: post_payload['featured_media'] = media_id

            wp_res = requests.post(WP_URL, auth=(WP_USER, WP_APP_PASSWORD), json=post_payload)
            
            if wp_res.status_code == 201:
                new_url = wp_res.json().get('link')
                print(f"  [+] Success! Article Live: {new_url}")
                SESSION_PROCESSED_URLS.add(article_link) # Add to memory
                ping_google_indexing(new_url)
            else:
                print(f"  [!] WordPress Error: {wp_res.status_code}")

        except Exception as e:
            print(f"General Error processing {feed_info['name']}: {e}")

        time.sleep(120)

if __name__ == "__main__":
    while True:
        run_aggregator()
        SESSION_PROCESSED_URLS.clear() # Clear memory every hour to prevent infinite RAM usage
        print("\nSweep Complete. Sleeping for 1 hour...")
        time.sleep(3600)