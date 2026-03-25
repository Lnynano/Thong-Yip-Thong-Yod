import requests
import os
from dotenv import load_dotenv

load_dotenv()
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def fetch_gold_news():
    url = "https://newsdata.io/api/1/latest"
    
    # เจาะจง Keywords ที่เกี่ยวกับตลาดทุนเท่านั้น เพื่อเลี่ยงข่าวขยะ
    search_query = '(gold AND (price OR market OR trading OR xauusd)) OR (fed AND "interest rate")'
    
    params = {
        "apikey": NEWS_API_KEY,
        "q": search_query,
        "language": "en",
        "category": "business,top" # บังคับหมวดหมู่
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10
        )
        if response.status_code != 200: return []
        
        articles = response.json().get("results", [])
        filtered_news = []
        
        # คำสั่งประหารข่าวขยะ (ถ้าเจอคำพวกนี้ ตัดทิ้งทันที)
        killer_keywords = [
            "wrestling", "tna", "potato", "sport", "football", 
            "gold coast", "medal", "olympic", "recipe", "jewelry"
        ]

        for article in articles:
            title = article.get("title", "")
            desc = article.get("description", "") or ""
            content = (title + desc).lower()

            # 1. เช็คว่ามีคำขยะมั้ย
            if any(bad in content for bad in killer_keywords):
                continue
            
            # 2. เช็คว่าเกี่ยวกับทอง/เศรษฐกิจจริงๆ มั้ย
            important_words = ["gold", "fed", "inflation", "usd", "economic", "market"]
            if not any(good in content for good in important_words):
                continue

            filtered_news.append({
                "title": title,
                "description": desc,
                "source": article.get("source_id"),
                "date": article.get("pubDate")
            })

        return filtered_news[:5]

    except Exception as e:
        print(f"Error: {e}")
        return []

if __name__ == "__main__":
    print("Fetching High-Quality Finance News...")
    news = fetch_gold_news()
    for i, n in enumerate(news):
        print(f"{i+1}. {n['title']}")
        print(f"   Source: {n['source']}")

def format_news_for_llm(news_list):

    combined_text = ""

    for i, news in enumerate(news_list):

        combined_text += (
            f"{i+1}. {news['title']}\n"
        )

    return combined_text