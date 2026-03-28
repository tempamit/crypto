import requests
import feedparser
import time # <-- Add this at the top
from google import genai

# ==========================================
# 1. YOUR CONFIGURATION (FILL THESE IN)
# ==========================================
WP_URL = "https://news.ipds.cloud/?rest_route=/wp/v2/posts"
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
        "name": "Bollywood Hungama (India)",
        "url": "https://www.bollywoodhungama.com/rss/news", 
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
    }
]

# ==========================================
# 3. HELPER FUNCTIONS (IMAGES & TAGS)
# ==========================================
def upload_image_to_wp(image_url, article_title):
    try:
        print("Downloading image from RSS...")
        img_data = requests.get(image_url, timeout=10).content
        
        # Clean up the title to make a safe filename
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
            
            # The JSON Prompt
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
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            # Clean and parse the JSON from Gemini
            raw_text = response.text.strip()
            if raw_text.startswith('```json'):
                raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith('```'):
                raw_text = raw_text[3:-3].strip()
                
            ai_data = json.loads(raw_text)
            
            # 2. Upload the Image (if we found one)
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
                "excerpt": ai_data['meta_description'], # Injects the SEO snippet
                "status": "publish", 
                "categories": feed_info['category_ids'],
                "tags": tag_ids
            }
            
            # Attach the image if successful
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
            continue 

# ==========================================
# 5. THE AUTOMATION LOOP
# ==========================================
if __name__ == "__main__":
    print("Full-Stack SEO News Engine Online.")
    while True:
        run_aggregator()
        print("\nSweep complete. Sleeping for 60 minutes...")
        time.sleep(3600)