import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def parse_page(source, url):
    print(f"\n==================== {source} ====================")
    r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
    print("Status:", r.status_code)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    count = 0
    if source == "Dosign":
        for a in soup.find_all('a', href=True):
            if '/vacature/' in a['href']:
                full_url = urljoin("https://www.dosign.nl", a['href'])
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    count += 1
                    print(f"[{count}] {title} -> {full_url}")
                    if count >= 3: break

    elif source == "Werkzoeken":
        for a in soup.find_all('a', href=True):
            if '/vacature/' in a['href'] and 'full-stack' not in a['href']:
                full_url = urljoin("https://www.werkzoeken.nl", a['href'])
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    count += 1
                    print(f"[{count}] {title} -> {full_url}")
                    if count >= 3: break

    elif source == "VNOM":
        for a in soup.find_all('a', href=True):
            if '/vacature/' in a['href']:
                full_url = urljoin("https://www.vnom.nl", a['href'])
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    count += 1
                    print(f"[{count}] {title} -> {full_url}")
                    if count >= 3: break

    elif source == "BlueBeaver":
        for a in soup.find_all('a', href=True):
            if '/opdracht' in a['href'] or '/zzp-' in a['href']:
                full_url = urljoin("https://bluebeaver.nl", a['href'])
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    count += 1
                    print(f"[{count}] {title} -> {full_url}")
                    if count >= 3: break

    elif source == "TechnischeVacaturebank":
        for a in soup.find_all('a', href=True):
            if '/vacature/' in a['href']:
                full_url = urljoin("https://www.technischevacaturebank.nl", a['href'])
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    count += 1
                    print(f"[{count}] {title} -> {full_url}")
                    if count >= 3: break

parse_page("Dosign", "https://www.dosign.nl/discipline/elektrotechniek/vacatures")
parse_page("Werkzoeken", "https://www.werkzoeken.nl/vacatures/?q=elektrotechniek")
parse_page("VNOM", "https://www.vnom.nl/vacatures/e-en-i-vacatures/")
parse_page("BlueBeaver", "https://www.bluebeaver.nl/zzp-opdrachten-elektrotechniek")
parse_page("TechnischeVacaturebank", "https://www.technischevacaturebank.nl/vacatures/")
