import httpx
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

dosign_urls = [
    "https://www.dosign.com/nl-nl/vacatures",
    "https://www.dosign.com/nl-nl/",
    "https://www.dosign.nl",
    "https://www.dosign.com/nl-nl/freelance-opdrachten",
    "https://www.dosign.com/nl-nl/opdrachten",
]

for url in dosign_urls:
    try:
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
        print(f"{url} -> {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            print("Title:", soup.title.string.strip() if soup.title else "No title")
    except Exception as e:
        print(f"{url} -> Error: {e}")
