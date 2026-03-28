import requests
import feedparser
import time
import json
import re
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build

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

# THE CASCADING FALLBACK LIST
FALLBACK_MODELS = [
    "gemini-2.5-flash",          # The standard 2.5 model (Usually has 1,500 free requests/day)
    "gemini-2.0-flash",          # Extremely stable high-capacity fallback
    "gemini-1.5-flash-latest"    # Explicit tag to force the 1.5 series to work
    "gemini-2.5-flash-lite"    # Backup 2: Experimental
    "gemini-3-flash-previ"
    "gemini-3.1-flash-lite-preview"
    "gemini-3.1-pro-preview"
]

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================

def ping_google_indexing(url):
    try:
        scopes = ["https://www.googleapis.com/auth/indexing"]
        credentials = service_account.Credentials.from_service_account_file(JSON_KEY_FILE, scopes=scopes)
        service = build("indexing", "v3", credentials=credentials)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        print(f"Google Indexing API: Successfully pinged {url}")
    except Exception as e:
        print(f"Google Indexing API Error: {e}")

def get_related_posts_html(category_id):
    try:
        params = {"categories": category_id, "per_page": 3, "status": "publish"}
        res = requests.get(WP_URL, params=params)
        if res.status_code == 200:
            posts = res.json()
            if not posts: return ""
            html = "<br><hr><h3>Related News You Might Like:</h3><ul>"
            for p in posts:
                html += f'<li><a href="{p["link"]}">{p["title"]["rendered"]}</a></li>'
            html += "</ul>"
            return html
    except: return ""
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
    {"name": "Variety Film (Hollywood)", "url": "https://variety.com/v/film/feed/", "category_ids": [8, 2]},
    {"name": "BBC Entertainment (Global)", "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "category_ids": [6]},
    {"name": "NME (Global Music)", "url": "https://www.nme.com/news/music/feed", "category_ids": [3, 6]},
    {"name": "E! Online Top Stories (Lifestyle)", "url": "https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml", "category_ids": [4, 5]},
    {"name": "Hindustan Times (OTT & Web Series)", "url": "https://www.hindustantimes.com/feeds/rss/entertainment/web-series/rssfeed.xml", "category_ids": [56]},
    {"name": "IGN (Global Gaming & Esports)", "url": "https://feeds.ign.com/ign/games-all", "category_ids": [57]},
    {"name": "Anime News Network (Anime & Manga)", "url": "https://www.animenewsnetwork.com/news/rss.xml", "category_ids": [58]},
    {"name": "Soompi (K-Pop & K-Drama)", "url": "https://www.soompi.com/feed", "category_ids": [59, 3]},
    {"name": "The Verge (Entertainment Tech)", "url": "https://www.theverge.com/rss/index.xml", "category_ids": [60]}
]

def run_aggregator():
    print("\nStarting Global SEO News Sweep...")
    for feed_info in FEEDS:
        print(f"\n--- Checking: {feed_info['name']} ---")
        try:
            feed = feedparser.parse(feed_info['url'])
            if not feed.entries: continue
            
            latest = feed.entries[0]
            original_title = latest.title
            summary = getattr(latest, 'summary', original_title)
            
            # Find Image
            image_url = None
            if 'media_content' in latest: image_url = latest.media_content[0]['url']
            elif 'links' in latest:
                for link in latest.links:
                    if 'image' in link.get('type', ''): image_url = link.href

            prompt = f"""
            You are a viral news writer. Rewrite this news into a 200-word conversational post. 
            Title: {original_title}
            Summary: {summary}

            MANDATORY: Return ONLY a valid JSON object. 
            Escape all double quotes within strings using a backslash.
            Structure:
            {{
              "article_html": "HTML post with <p> and <strong> tags",
              "meta_description": "150-char SEO snippet",
              "tags": ["trending_keyword1", "trending_keyword2"]
            }}
            """
            
            # --- THE FALLBACK LOGIC ---
            ai_data = None
            for model_name in FALLBACK_MODELS:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    raw_text = response.text.strip()
                    raw_text = re.sub(r'^```json\s*|\s*```$', '', raw_text, flags=re.MULTILINE)
                    ai_data = json.loads(raw_text)
                    break # Success! Break out of the fallback loop
                
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        print(f"  [!] Quota exhausted for {model_name}. Switching to next model...")
                        continue # Move to the next model in the list
                    else:
                        print(f"  [!] Formatting error with {model_name}: {e}")
                        break # Break loop if it's a JSON/parsing error, not a quota issue

            # If all models failed or got exhausted
            if not ai_data:
                print("  [X] All models exhausted or failed. Cooling down for 60 seconds...")
                time.sleep(60)
                continue # Skip this article and move to the next feed

            # Build Final Content with Internal Links
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
                print(f"Success! Article Live: {new_url}")
                ping_google_indexing(new_url)
            else:
                print(f"WordPress Error: {wp_res.status_code}")

        except Exception as e:
            print(f"General Error processing {feed_info['name']}: {e}")

        print("Pausing for 30 seconds...")
        time.sleep(30)

if __name__ == "__main__":
    while True:
        run_aggregator()
        print("\nSweep Complete. Sleeping for 1 hour...")
        time.sleep(3600)