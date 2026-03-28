import requests
import feedparser
import time
import json
import re
from google import genai
# NEW IMPORTS FOR INDEXING
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# 1. YOUR CONFIGURATION
# ==========================================
WP_URL = "https://news.ipds.cloud/wp-json/wp/v2/posts"
WP_MEDIA_URL = "https://news.ipds.cloud/wp-json/wp/v2/media"  
WP_TAGS_URL = "https://news.ipds.cloud/wp-json/wp/v2/tags"    

WP_USER = "adminipds"  # The username you use to log in
WP_APP_PASSWORD = "Jjkr amue uHw0 tGDx OCKu iJYz"  # The one you generated in WP

# Paste your Google AI Studio key here
GEMINI_API_KEY = "AIzaSyCURIszps9ihHRA-CFap3xAHriZcJf2g6c"

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. MULTI-COUNTRY FEED DICTIONARY
# ==========================================
FEEDS = [
    {
        "name": "FilmiBeat Bollywood (India)",
        "url": "https://www.filmibeat.com/rss/feeds/bollywood-fb.xml", 
        "category_ids": [7, 2]  
    },
    {
        "name": "Times of India (Bollywood)",
        "url": "https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms", 
        "category_ids": [7, 2]  
    },
    {
        "name": "Variety Film (Hollywood)",
        "url": "https://variety.com/v/film/feed/", 
        "category_ids": [8, 2]  
    },
    {
        "name": "BBC Entertainment (Global)",
        "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", 
        "category_ids": [6]     
    },
    {
        "name": "NME (Global Music)",
        "url": "https://www.nme.com/news/music/feed", 
        "category_ids": [3, 6]  
    },
    {
        "name": "E! Online Top Stories (Lifestyle)",
        "url": "https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml", 
        "category_ids": [4, 5]  
    },
    {
        "name": "Hindustan Times (OTT & Web Series)",
        "url": "https://www.hindustantimes.com/feeds/rss/entertainment/web-series/rssfeed.xml", 
        "category_ids": [56]  
    },
    {
        "name": "IGN (Global Gaming & Esports)",
        "url": "https://feeds.ign.com/ign/games-all", 
        "category_ids": [57]  
    },
    {
        "name": "Anime News Network (Anime & Manga)",
        "url": "https://www.animenewsnetwork.com/news/rss.xml", 
        "category_ids": [58]  
    },
    {
        "name": "Soompi (K-Pop & K-Drama)",
        "url": "https://www.soompi.com/feed", 
        "category_ids": [59, 3]  
    },
    {
        "name": "The Verge (Entertainment Tech)",
        "url": "https://www.theverge.com/rss/index.xml", 
        "category_ids": [60]  
    }
]
# ==========================================
# NEW: GOOGLE INDEXING FUNCTION
# ==========================================
def ping_google_indexing(url):
    try:
        scopes = ["https://www.googleapis.com/auth/indexing"]
        credentials = service_account.Credentials.from_service_account_file(
            JSON_KEY_FILE, scopes=scopes
        )
        service = build("indexing", "v3", credentials=credentials)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        print(f"Google Indexing API: Successfully pinged {url}")
    except Exception as e:
        print(f"Google Indexing API Error: {e}")

# ==========================================
# 3. HELPER FUNCTIONS (IMAGES & TAGS)
# ==========================================
def upload_image_to_wp(image_url, article_title):
    try:
        print("Downloading image from RSS...")
        img_data = requests.get(image_url, timeout=10).content
        
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', article_title)[:30]
        
        headers = {
            "Content-Type": "image/jpeg",
            "Content-Disposition": f"attachment; filename={safe_name}.jpg"
        }
        
        print("Uploading image to WordPress Media Library...")
        res = requests.post(WP_MEDIA_URL, headers=headers, data=img_data, auth=(WP_USER, WP_APP_PASSWORD))
        
        if res.status_code == 201:
            print("Image uploaded successfully!")
            return res.json()['id']
    except Exception as e:
        print(f"Failed to process image: {e}")
    return None

def get_or_create_tags(tag_names):
    tag_ids = []
    for tag in tag_names:
        res = requests.post(WP_TAGS_URL, auth=(WP_USER, WP_APP_PASSWORD), json={"name": tag})
        if res.status_code == 201:
            tag_ids.append(res.json()['id'])
        elif res.status_code == 400 and 'term_exists' in res.text:
            tag_ids.append(res.json()['data']['term_id'])
    return tag_ids

# ==========================================
# 4. FETCH, REWRITE, AND POST
# ==========================================
#
def run_aggregator():
    print("\nStarting SEO-Optimized News Sweep...")
    
    for feed_info in FEEDS:
        print(f"\n--- Checking: {feed_info['name']} ---")
        
        try:
            feed = feedparser.parse(feed_info['url'])
            if not feed.entries:
                continue

            latest_article = feed.entries[0]
            original_title = latest_article.title
            
            # 1. Try to find an image in the RSS feed
            image_url = None
            if 'media_content' in latest_article:
                image_url = latest_article.media_content[0]['url']
            elif 'links' in latest_article:
                for link in latest_article.links:
                    if 'image' in link.get('type', ''):
                        image_url = link.href

            summary = getattr(latest_article, 'summary', original_title) 

            print(f"Found: {original_title}")
            print("Handing over to Gemini for Article, Meta Description, and Tags...")
            
            prompt = f"""
            You are an enthusiastic pop-culture fanatic. Read the news summary and rewrite it into a 200-250 word update. 
            Original Title: {original_title}
            Original Context: {summary}
            
            Apply these transformations strictly:
            - Tone: Casual, highly enthusiastic, conversational. 
            - Rhythm: Vary sentence lengths aggressively. Mix punchy fragments with longer thoughts. 
            - Structure: Avoid standard "Intro-Body-Conclusion". Start mid-thought.
            - Formatting: HTML format (<p>, <strong>). NO title. NO source links.
            
            YOU MUST OUTPUT YOUR RESPONSE AS A VALID JSON OBJECT EXACTLY LIKE THIS:
            {{
                "article_html": "your html content here",
                "meta_description": "A punchy, 150-character SEO summary of the article.",
                "tags": ["keyword1", "keyword2", "keyword3"]
            }}
            """
            
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt
            )
            
            # THE FIX: Safely strip markdown block indicators from the JSON output
            raw_text = response.text.strip()
            raw_text = raw_text.replace("```json", "").replace("```html", "").replace("```", "").strip()
                
            ai_data = json.loads(raw_text)
            
            # 2. Upload the Image 
            media_id = None
            if image_url:
                media_id = upload_image_to_wp(image_url, original_title)

            # 3. Create the Tags in WordPress
            print("Generating SEO tags...")
            tag_ids = get_or_create_tags(ai_data['tags'])
            
            # 4. Push the Ultimate Payload
            post_data = {
                "title": original_title, 
                "content": ai_data['article_html'],
                "excerpt": ai_data['meta_description'], 
                "status": "publish", 
                "categories": feed_info['category_ids'],
                "tags": tag_ids
            }
            
            if media_id:
                post_data['featured_media'] = media_id
            
            print("Pushing fully optimized article to news.ipds.cloud...")
            response = requests.post(WP_URL, auth=(WP_USER, WP_APP_PASSWORD), json=post_data)
            
            if response.status_code == 201:
                print(f"Success! Article is Live with SEO Meta, Tags, and Image.")
            else:
                print(f"Error pushing to WP: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"Error processing {feed_info['name']}: {e}")
            
        print("Pausing for 30 seconds to respect API rate limits...")
        time.sleep(30)


# ==========================================
# 5. THE AUTOMATION LOOP
# ==========================================
if __name__ == "__main__":
    print("Full-Stack SEO News Engine Online.")
    while True:
        run_aggregator()
        print("\nSweep complete. Sleeping for 60 minutes...")
        time.sleep(3600)