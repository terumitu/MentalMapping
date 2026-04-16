import urllib.request
import json
import streamlit as st

url = st.secrets["DISCORD_WEBHOOK_URL"]
print(f"URL: {url}")
data = json.dumps({"content": "テスト"}).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "MentalMapping/1.0"})
res = urllib.request.urlopen(req)
print(f"Status: {res.status}")
