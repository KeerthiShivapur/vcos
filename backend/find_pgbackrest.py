import urllib.request
import re

# Get the download page
url = 'https://pgbackrest.org/download.html'
try:
    with urllib.request.urlopen(url) as response:
        html = response.read().decode('utf-8')
        # Find Windows download links
        links = re.findall(r'href=["\']([^"\']*windows[^"\']*\.zip)["\']', html, re.IGNORECASE)
        for link in links:
            print('Found:', link)
        if not links:
            # Try to find any .zip links
            links = re.findall(r'href=["\']([^"\']*\.zip)["\']', html)
            for link in links[:20]:
                print('Zip:', link)
except Exception as e:
    print('Error:', e)