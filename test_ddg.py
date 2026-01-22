from duckduckgo_search import DDGS
import time

print("Testing DDGS...")
try:
    with DDGS() as ddgs:
        results = list(ddgs.images("Nike shoes", max_results=3))
        print(f"Success! Found {len(results)} images.")
        for r in results:
            print(f"- {r['title']}")
except Exception as e:
    print(f"Error: {e}")
