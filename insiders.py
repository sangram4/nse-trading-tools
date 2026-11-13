#!/usr/bin/env python3
"""
insiders.py -- NSE insider trades (PIT) and bulk/block deals (own build)

Usage:
  python3 insiders.py --symbol APTUS
"""
import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
API = "https://www.nseindia.com/api/"
ARCH = "https://nsearchives.nseindia.com/content/equities/"


def get(url, referer=True, pause=0.3):
    time.sleep(pause)
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = "https://www.nseindia.com/"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return None


def parse_deals(text, kind):
    rows = []
    for r in csv.DictReader(io.StringIO(text.replace("\r", ""))):
        if (r.get("Date") or "").upper().startswith("NO RECORDS") or not r.get("Symbol"):
            continue
        q = num(r.get("Quantity Traded"))
        px = num(r.get("Trade Price / Wght. Avg. Price"))
        rows.append({"kind": kind, "date": r["Date"], "symbol": r["Symbol"],
                     "client": r.get("Client Name", "?"), "side": (r.get("Buy/Sell") or "").upper(),
                     "qty": q, "price": px})
    return rows


def fetch_deals(symbol=None):
    try:
        bulk = parse_deals(get(ARCH + "bulk.csv", referer=False), "bulk")
        block = parse_deals(get(ARCH + "block.csv", referer=False), "block")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        return None, str(e)
    rows = bulk + block
    if symbol:
        rows = [r for r in rows if r["symbol"].upper() == symbol.upper()]
    return rows, None


def fetch_insiders(symbol):
    url = API + "corporates-pit?index=equities&symbol=" + urllib.parse.quote(symbol.upper())
    try:
        doc = json.loads(get(url))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        return None, str(e)
    except json.JSONDecodeError as e:
        return None, f"bad response: {e}"
    rows = []
    for r in doc.get("data") or []:
        rows.append({"filed": r.get("date"), "who": r.get("acqName"),
                     "category": r.get("personCategory"), "type": r.get("tdpTransactionType"),
                     "mode": r.get("acqMode"), "shares": num(r.get("secAcq"))})
    return rows, None


def main():
    ap = argparse.ArgumentParser(description="NSE insider trades and bulk/block deals (own build)")
    ap.add_argument("--symbol", required=True)
    args = ap.parse_args()
    symbol = args.symbol.upper()

    print(f"Insider trading and bulk/block deals for {symbol}:\n")

    rows, err = fetch_insiders(symbol)
    if rows is None:
        print(f"  Insider (PIT) trades: could not fetch ({err})")
    elif not rows:
        print("  Insider (PIT) trades: none found.")
    else:
        print("  Insider (PIT) trades:")
        for r in rows[:10]:
            print(f"    filed {r['filed']}  {r['who']}  ({r['category']})  {r['type']}  "
                  f"{r['mode']}  {r['shares']} shares")

    print()
    deals, err = fetch_deals(symbol)
    if deals is None:
        print(f"  Bulk/block deals (today): could not fetch ({err})")
    elif not deals:
        print("  Bulk/block deals (today): none found for this symbol today.")
    else:
        print("  Bulk/block deals (today):")
        for d in deals[:10]:
            print(f"    {d['kind']:<5} {d['date']}  {d['client']}  {d['side']}  "
                  f"{d['qty']} sh @ {d['price']}")

    print("\nDisclosures of what others did, days late: not a signal to copy.")


if __name__ == "__main__":
    main()