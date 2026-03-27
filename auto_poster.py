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
# Mapping the exact category IDs you extracted from news.ipds.cloud
FEEDS = [
    {
        "name": "Bollywood Hungama (India / UAE)",
        "url": "https://www.bollywoodhungama.com/rss/news", 
        "category_ids": [7, 2]  # Bollywood, Movies
    },
    {
        "name": "Variety Film (US / Hollywood)",
        "url": "https://variety.com/v/film/feed/", 
        "category_ids": [8, 2]  # Hollywood, Movies
    },
    {
        "name": "BBC Entertainment (UK / Global)",
        "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", 
        "category_ids": [6]     # Global
    },
    {
        "name": "NME (Global Music)",
        "url": "https://www.nme.com/news/music/feed", 
        "category_ids": [3, 6]  # Music, Global
    },
    {
        "name": "E! Online Top Stories (Celebrity / Lifestyle)",
        "url": "https://www.eonline.com/syndication/feeds/rssfeeds/topstories.xml", 
        "category_ids": [4, 5]  # Celebrities, Lifestyle
    }
]

# ==========================================
# 3. FETCH, REWRITE, AND POST
# ==========================================
def run_aggregator():
    print("Starting news sweep across all regions...")
    
    for feed_info in FEEDS:
        print(f"\n--- Checking: {feed_info['name']} ---")
        
        try:
            feed = feedparser.parse(feed_info['url'])
            
            if not feed.entries:
                print("No articles found in this feed right now.")
                continue

            latest_article = feed.entries[0]
            original_title = latest_article.title
            link = latest_article.link
            summary = getattr(latest_article, 'summary', original_title) 

            print(f"Found: {original_title}")
            print("Rewriting with Gemini 2.5 Flash...")
            
            prompt = f"""
            Act as an expert entertainment journalist. Read the following news summary and rewrite it into a fresh, engaging, and SEO-optimized 150-word news update. 
            Format the output in clean HTML (use <p> tags for paragraphs and <strong> for emphasis). 
            Do not include a title in your output.
            
            Original Title: {original_title}
            Original Context: {summary}
            
            At the very end of the article, add this exact HTML string: 
            <p><em>Source: <a href="{link}" target="_blank" rel="noopener">Read the full story here</a></em></p>
            """
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            ai_rewritten_content = response.text
            
            # WordPress payload: Pushing LIVE to your specific category IDs
            post_data = {
                "title": original_title, 
                "content": ai_rewritten_content,
                "status": "publish", 
                "categories": feed_info['category_ids'] 
            }
            
            response = requests.post(WP_URL, auth=(WP_USER, WP_APP_PASSWORD), json=post_data)
            
            if response.status_code == 201:
                print(f"Success! Published live to categories: {feed_info['category_ids']}.")
            else:
                print(f"Error pushing to WP: {response.status_code}")
                
        except Exception as e:
            print(f"Error processing {feed_info['name']}: {e}")
            continue 

# ==========================================
# 4. THE AUTOMATION LOOP
# ==========================================
if __name__ == "__main__":
    print("Global Multi-Category News Engine Online.")
    while True:
        run_aggregator()
        print("\nSweep complete. Sleeping for 60 minutes...")
        time.sleep(3600)