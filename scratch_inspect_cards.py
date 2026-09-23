import httpx
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def inspect_site(name, url):
    print(f"\n==================== {name} ====================")
    r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        if len(text) > 10 and not any(skip in href for skip in ['#', 'javascript:', 'login', 'register', 'contact', 'privacy', 'cookie', 'over-ons', 'branche', 'discipline']):
            print(f"Text: {text[:60]} | Href: {href}")

inspect_site("Dosign", "https://www.dosign.nl/discipline/elektrotechniek/vacatures")
inspect_site("VNOM", "https://www.vnom.nl/vacatures/e-en-i-vacatures/")
inspect_site("BlueBeaver", "https://www.bluebeaver.nl/zzp-opdrachten-elektrotechniek")
inspect_site("TechnischeVacaturebank", "https://www.technischevacaturebank.nl/vacatures/zoeken?zoekterm=elektrotechniek")
