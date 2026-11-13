#!/usr/bin/env python3
"""
news.py -- NSE news monitor: Google News headlines + NSE corporate
announcements (own build, stdlib only)

Usage:
  python3 news.py --symbol APTUS
  python3 news.py --symbol RELIANCE --hours 24
"""
import argparse
import http.cookiejar
import sys
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta


def fetch_google_news(symbol, hours):
    query = urllib.parse.quote(f"{symbol} NSE")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        return None, str(e)

    items = []
    try:
        root = ET.fromstring(data)
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pubdate = item.findtext("pubDate", "")
            items.append({"title": title, "link": link, "pubdate": pubdate})
    except ET.ParseError as e:
        return None, f"could not parse feed: {e}"
    return items[:10], None


def fetch_nse_announcements(symbol):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        req = urllib.request.Request("https://www.nseindia.com", headers=headers)
        opener.open(req, timeout=10)  # get cookies
        url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}"
        req2 = urllib.request.Request(url, headers={**headers, "Referer": "https://www.nseindia.com/"})
        with opener.open(req2, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        return None, str(e)
    except json.JSONDecodeError as e:
        return None, f"bad response: {e}"
    return data[:10] if isinstance(data, list) else [], None


def main():
    ap = argparse.ArgumentParser(description="NSE news monitor (own build)")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--hours", type=int, default=24)
    args = ap.parse_args()
    symbol = args.symbol.upper()

    print(f"News for {symbol} (last {args.hours}h, best-effort):\n")

    news, err = fetch_google_news(symbol, args.hours)
    if news is None:
        print(f"  Google News: could not fetch ({err})")
    elif not news:
        print("  Google News: nothing found.")
    else:
        print("  Google News:")
        for n in news:
            print(f"    {n['pubdate']}  {n['title']}")
            print(f"      {n['link']}")

    print()
    ann, err = fetch_nse_announcements(symbol)
    if ann is None:
        print(f"  NSE announcements: could not fetch ({err})")
    elif not ann:
        print("  NSE announcements: nothing found (or NSE blocked the request).")
    else:
        print("  NSE announcements:")
        for a in ann:
            subject = a.get("subject") or a.get("desc") or "(no subject)"
            dt = a.get("an_dt") or a.get("attchmntDate") or ""
            print(f"    {dt}  {subject}")

    print("\nHeadlines are leads, not facts. Open the source before acting on it.")


if __name__ == "__main__":
    main()