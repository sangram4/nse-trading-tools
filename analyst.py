#!/usr/bin/env python3
"""
analyst.py -- NSE quarterly results reader via XBRL filings (own build)

Usage:
  python3 analyst.py --symbol RELIANCE
"""
import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
RESULTS = "https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=%s&period=Quarterly"

TAGS = {
    "revenue": ["RevenueFromOperations"],
    "pbt": ["ProfitBeforeTax"],
    "net_profit": ["ProfitLossForPeriod", "ProfitLossForPeriodFromContinuingOperations"],
    "eps": ["DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
            "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations"],
}


def get(url, pause=0.3):
    time.sleep(pause)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.nseindia.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_xbrl(data):
    """XBRL bytes -> {key: value} for the reporting quarter (OneD context)."""
    root = ET.fromstring(data)
    facts = {}
    for el in root.iter():
        name = el.tag.rsplit("}", 1)[-1]
        if el.get("contextRef") and (el.text or "").strip():
            facts.setdefault(name, []).append((el.get("contextRef"), el.text.strip()))
    out = {}
    for key, names in TAGS.items():
        for n in names:
            vals = [v for c, v in facts.get(n, []) if c == "OneD"]
            if vals:
                try:
                    out[key] = float(vals[0])
                except ValueError:
                    pass
                break
    return out


def fetch_quarters(symbol, n=5):
    url = RESULTS % urllib.parse.quote(symbol.upper())
    try:
        rows = json.loads(get(url))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        return None, str(e)
    except json.JSONDecodeError as e:
        return None, f"bad response: {e}"

    picked = sorted(
        (r for r in rows if r.get("consolidated") == "Consolidated" and r.get("xbrl")),
        key=lambda r: datetime.datetime.strptime(r["toDate"], "%d-%b-%Y"), reverse=True
    )[:n]

    if not picked:
        return None, "no consolidated quarterly results with an XBRL link found"

    out = []
    for r in picked:
        try:
            nums = parse_xbrl(get(r["xbrl"]))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ET.ParseError) as e:
            nums = {"error": str(e)}
        out.append({"to": r["toDate"], **nums})
    return out, None


def cr(v):
    return "n/a" if v is None else "Rs {:,.0f} cr".format(v / 1e7)


def main():
    ap = argparse.ArgumentParser(description="NSE quarterly results via XBRL (own build)")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--quarters", type=int, default=4)
    args = ap.parse_args()

    qs, err = fetch_quarters(args.symbol, args.quarters)
    if qs is None:
        print(f"analyst.py: could not get results for {args.symbol}: {err}", file=sys.stderr)
        sys.exit(1)

    print(f"{args.symbol.upper()} quarterly results (consolidated, from NSE XBRL filings):\n")
    for q in qs:
        if "error" in q:
            print(f"  {q['to']}: could not read the filing ({q['error']})")
            continue
        print(f"  Quarter ending {q['to']}")
        print(f"    Revenue: {cr(q.get('revenue'))}")
        print(f"    Profit before tax: {cr(q.get('pbt'))}")
        print(f"    Net profit: {cr(q.get('net_profit'))}")
        print(f"    Diluted EPS: Rs {q['eps']:.2f}" if q.get('eps') is not None else "    Diluted EPS: n/a")
        print()

    print("Reported numbers, not a forecast. Net profit can include one-offs. Not financial advice.")


if __name__ == "__main__":
    main()