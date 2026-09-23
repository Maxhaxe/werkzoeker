import httpx, re

url = 'https://striive.com/nl/opdrachten'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
r = httpx.get(url, headers=headers, verify=False, follow_redirects=True)

urls = re.findall(r'https?://[^\s\"\'<>]+', r.text)
print("Striive APIs / endpoints found:")
for u in set(urls):
    if any(k in u.lower() for k in ('api', 'opdracht', 'vacancy', 'search', 'graphql')):
        print(" ->", u)
