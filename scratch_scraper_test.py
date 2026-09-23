import httpx
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def test_site(name, url):
    print(f"\n=== {name} ({url}) ===")
    try:
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=10.0)
        print(f"Status: {r.status_code}")
        soup = BeautifulSoup(r.text, 'html.parser')
        print("Title:", soup.title.string.strip() if soup.title and soup.title.string else "No title")
        links = [a.get('href') for a in soup.find_all('a') if a.get('href')]
        print(f"Total links: {len(links)}")
        sample_links = [l for l in links if 'opdracht' in l or 'vacature' in l or 'detail' in l or 'job' in l or 'project' in l][:5]
        print("Sample job links:", sample_links)
    except Exception as e:
        print(f"Error: {e}")

test_site("1. Freelance.nl category", "https://www.freelance.nl/opdrachten/systeem-componentintegratie")
test_site("2. Werkzoeken", "https://www.werkzoeken.nl/vacatures/?q=elektrotechniek")
test_site("3. VNOM", "https://www.vnom.nl/vacatures")
test_site("4. BlueBeaver", "https://bluebeaver.nl/opdrachten/")
test_site("5. Technische Vacaturebank", "https://www.technischevacaturebank.nl/vacatures/")
test_site("6. Dosign", "https://www.dosign.com/nl-nl/vacatures/")
