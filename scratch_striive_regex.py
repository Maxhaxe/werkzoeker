import httpx, re
from urllib.parse import urljoin

url = 'https://striive.com/nl/opdrachten'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

r = httpx.get(url, headers=headers, verify=False, follow_redirects=True)
print("Striive response status:", r.status_code)

# Find URLs matching /nl/opdracht/...
urls = set(re.findall(r'/nl/opdracht/[a-zA-Z0-9%\-]+', r.text))
print(f"Found {len(urls)} job assignment URLs in Striive HTML!")
for u in list(urls)[:10]:
    # Extract human readable title from slug
    slug = u.split('/')[-1]
    title = slug.replace('-', ' ').title()
    full_url = urljoin('https://striive.com', u)
    print(f"Job: {title} -> {full_url}")
