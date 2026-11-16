"""Dependency-light DuckDuckGo HTML search adapter."""
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urlparse
import requests
from . import config

class ResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.current = None
        self.capture = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self.current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self.items.append(self.current)
            self.capture = "title"
        elif "result__snippet" in classes and self.current:
            self.capture = "snippet"
    def handle_data(self, data):
        if self.current and self.capture:
            self.current[self.capture] += data
    def handle_endtag(self, tag):
        if tag == "a": self.capture = None

def _valid_url(raw):
    raw = unescape(raw.strip())
    if raw.startswith("//"): raw = "https:" + raw
    parsed = urlparse(raw)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        raw = parse_qs(parsed.query).get("uddg", [""])[0]
        parsed = urlparse(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""

def search(query, limit=None):
    if not config.WEB_SEARCH_ENABLED or not query.strip(): return []
    try:
        response = requests.post(config.WEB_SEARCH_URL, data={"q": query[:300]}, headers={"User-Agent": "Mozilla/5.0 (compatible; OfflineTutor/1.0)"}, timeout=(4, config.WEB_SEARCH_TIMEOUT))
        response.raise_for_status()
    except requests.RequestException:
        return []
    parser = ResultParser()
    parser.feed(response.text)
    output, seen = [], set()
    for item in parser.items:
        url = _valid_url(item["url"])
        title = re.sub(r"\\s+", " ", item["title"]).strip()
        snippet = re.sub(r"\\s+", " ", item["snippet"]).strip()
        if not url or url in seen or not title: continue
        seen.add(url)
        output.append({"title": title[:200], "url": url, "snippet": snippet[:700]})
        if len(output) >= (limit or config.WEB_SEARCH_TOP_K): break
    return output
