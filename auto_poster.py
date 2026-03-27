import requests
import feedparser
import time # <-- Add this at the top
from google import genai

# ==========================================
# 1. YOUR CONFIGURATION (FILL THESE IN)
# ==========================================
WP_URL = "https://news.ipds.cloud/wp-json/wp/v2/posts"
WP_USER = "adminipds"  # The username you use to log in
WP_APP_PASSWORD = "Jjkr amue uHw0 tGDx OCKu iJYz"  # The one you generated in WP

# Paste your Google AI Studio key here
GEMINI_API_KEY = "AIzaSyCURIszps9ihHRA-CFap3xAHriZcJf2g6c"

RSS_FEED = "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"

# Initialize the new Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. FETCH, REWRITE, AND POST
# ==========================================
def fetch_rewrite_and_post():
    print(f"Fetching news from {RSS_FEED}...")
    feed = feedparser.parse(RSS_FEED)
    
    if not feed.entries:
        print("Error: No articles found.")
        return

    latest_article = feed.entries[0]
    original_title = latest_article.title
    link = latest_article.link
    
    summary = getattr(latest_article, 'summary', original_title) 

    print(f"Found: {original_title}")
    print("Handing over to Gemini to rewrite and optimize for SEO...")
    
    # ------------------------------------------
    # THE AI PROMPT
    # ------------------------------------------
    prompt = f"""
    Act as an expert entertainment journalist. Read the following news summary and rewrite it into a fresh, engaging, and SEO-optimized 150-word news update. 
    Format the output in clean HTML (use <p> tags for paragraphs and <strong> for emphasis). 
    Do not include a title in your output, just the article body.
    
    Original Title: {original_title}
    Original Context: {summary}
    
    At the very end of the article, add this exact HTML string: 
    <p><em>Source: <a href="{link}" target="_blank" rel="noopener">Read the full story here</a></em></p>
    """
    
    try:
        # Using the new SDK and the latest 2.5 flash model
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        ai_rewritten_content = response.text
        print("Gemini successfully wrote a brand new article!")
    except Exception as e:
        print(f"Error with the AI generation: {e}")
        return

    # ------------------------------------------
    # PUSH TO WORDPRESS
    # ------------------------------------------
    post_data = {
        "title": original_title, 
        "content": ai_rewritten_content,
        "status": "draft" 
    }
    
    print("Pushing AI-generated article to news.ipds.cloud...")
    
    response = requests.post(WP_URL, auth=(WP_USER, WP_APP_PASSWORD), json=post_data)
    
    if response.status_code == 201:
        print("Success! The AI-written article is waiting in your WordPress dashboard.")
    else:
        print(f"Error pushing to WP: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    fetch_rewrite_and_post()

    # ==========================================
# 3. THE AUTOMATION LOOP
# ==========================================
if __name__ == "__main__":
    print("Starting 24/7 News Automation Engine...")
    while True:
        try:
            fetch_rewrite_and_post()
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            
        print("Task complete. Sleeping for 60 minutes...")
        time.sleep(3600) # 3600 seconds = 1 hour. Change this number to adjust frequency.