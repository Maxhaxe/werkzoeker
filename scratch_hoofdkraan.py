import httpx
from bs4 import BeautifulSoup

url = 'https://www.hoofdkraan.nl/opdrachten'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
r = httpx.get(url, headers=headers, follow_redirects=True)
soup = BeautifulSoup(r.text, 'html.parser')

print("All links sample:")
for a in soup.find_all('a', href=True)[:30]:
    print(a['href'], "->", a.get_text(strip=True)[:50])
