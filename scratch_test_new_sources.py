import httpx
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

candidates = [
    ("Hoofdkraan", "https://www.hoofdkraan.nl/opdrachten"),
    ("NationaleVacaturebank", "https://www.nationalevacaturebank.nl/vacatures/vakgebied/techniek"),
    ("Jobbird", "https://nl.jobbird.com/vacatures?q=elektrotechniek"),
    ("Careerjet", "https://www.careerjet.nl/vacatures-elektrotechniek.html"),
    ("Monsterboard", "https://www.monsterboard.nl/vacatures/zoeken/?q=elektrotechniek"),
]

for name, url in candidates:
    try:
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
        print(f"\n=== {name} ({url}) ===")
        print("Status:", r.status_code)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            print("Title:", soup.title.string.strip() if soup.title and soup.title.string else "No title")
            links = [a.get('href') for a in soup.find_all('a') if a.get('href')]
            print(f"Total links: {len(links)}")
            sample = [l for l in links if any(k in l.lower() for k in ('opdracht', 'vacature', 'job', 'detail'))][:5]
            print("Sample job links:", sample)
    except Exception as e:
        print(f"=== {name} Error ===")
        print(e)
