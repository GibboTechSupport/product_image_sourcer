import requests
from bs4 import BeautifulSoup
import json
import re
from fake_useragent import UserAgent

def search_bing(query):
    ua = UserAgent()
    headers = {"User-Agent": ua.random}
    url = f"https://www.bing.com/images/search?q={query}&form=HDRSC2&first=1"
    
    print(f"Testing Bing Search: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Bing usually puts metadata in 'm' attribute of 'a' tag with class 'iusc'
        results = []
        for a in soup.find_all('a', class_='iusc'):
            try:
                m = a.get('m')
                if m:
                    data = json.loads(m)
                    link = data.get('murl')
                    title = data.get('t') # 't' is usually title
                    if not title:
                        title = data.get('desc') # fallback
                    
                    results.append({'image': link, 'title': title})
                    if len(results) >= 3:
                        break
            except Exception as e:
                print(e)
                continue
                
        return results
    except Exception as e:
        print(f"Error: {e}")
        return []

res = search_bing("Nike Air Max 270")
for r in res:
    print(r)
