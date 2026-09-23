import httpx
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

sites = [
    ("Matchd", "https://www.matchd.nl/opdrachten"),
    ("EngineeringNet", "https://www.engineeringnet.nl/"),
    ("Hoofdkraan", "https://www.hoofdkraan.nl/opdrachten"),
    ("Freelancenetwerk", "https://www.freelancenetwerk.nl/opdrachten"),
]

for name, url in sites:
    try:
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
        print(f"\n=== {name} ({url}) ===")
        print("Status:", r.status_code)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            print("Title:", soup.title.string.strip() if soup.title else "No title")
            links = [a['href'] for a in soup.find_all('a', href=True)]
            print(f"Total links: {len(links)}")
            sample = [l for l in links if any(k in l.lower() for k in ('opdracht', 'vacature', 'job'))][:5]
            print("Sample job links:", sample)
    except Exception as e:
        print(f"=== {name} Error ===")
        print(e)
