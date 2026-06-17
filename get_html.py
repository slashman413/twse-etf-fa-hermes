import urllib.request
r = urllib.request.urlopen("http://localhost:8080/dashboard.html")
html = r.read().decode("utf-8")
# Find the script section
idx = html.find("<script>")
if idx >= 0:
    print(html[idx:idx+3000])
else:
    print("No <script> found")
    print(html[1000:2000])
