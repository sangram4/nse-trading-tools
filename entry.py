#!/usr/bin/env python3
"""
entry.py -- NSE opening-range breakout entry timer (own build, stdlib only)
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)


def fetch_intraday(symbol, range_days="5d", interval="5m"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
           f"?range={range_days}&interval={interval}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        return None, str(e)
    try:
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        q = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return None, "no data in response"
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        ist = datetime.utcfromtimestamp(t) + IST_OFFSET
        bars.append({"dt": ist, "open": o, "high": h, "low": l, "close": c})
    return bars, None


def bars_for_date(bars, date_str):
    return [b for b in bars if b["dt"].strftime("%Y-%m-%d") == date_str]


def main():
    ap = argparse.ArgumentParser(description="NSE opening-range entry timer (own build)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check")
    check.add_argument("symbol")
    check.add_argument("--now", help='pretend it is this IST time, e.g. "2026-11-09 10:00"')
    check.add_argument("--write", action="store_true")
    check.add_argument("--out", default="trader/entry.json")
    check.add_argument("--json", action="store_true")
    args = ap.parse_args()
    symbol = args.symbol.upper()
    bars, err = fetch_intraday(symbol)
    if bars is None:
        print(f"entry.py: could not fetch {symbol}: {err}", file=sys.stderr)
        sys.exit(1)
    if args.now:
        now = datetime.strptime(args.now, "%Y-%m-%d %H:%M")
        date_str = now.strftime("%Y-%m-%d")
    else:
        now = datetime.utcnow() + IST_OFFSET
        date_str = now.strftime("%Y-%m-%d")
    day_bars = bars_for_date(bars, date_str)
    if not day_bars:
        print(f"{symbol}.NS  {date_str}  no bars for this date "
              "(holiday, weekend, or too far back for Yahoo's 5-day window)")
        sys.exit(1)
    closed_bars = [b for b in day_bars if b["dt"] <= now]
    if len(closed_bars) < 3:
        print(f"{symbol}.NS  {now.strftime('%a %Y-%m-%d %H:%M')} IST  "
              f"opening range still forming ({len(closed_bars)} of 3 range bars closed)")
        sys.exit(0)
    range_bars = closed_bars[:3]
    range_high = max(b["high"] for b in range_bars)
    range_low = min(b["low"] for b in range_bars)
    result = {"symbol": symbol, "date": date_str, "range_high": round(range_high, 2),
              "range_low": round(range_low, 2), "status": None,
              "trigger_time": None, "trigger_price": None}
    triggered = None
    for b in closed_bars[3:]:
        if b["close"] > range_high:
            triggered = b
            break
    print(f"{symbol}.NS  {now.strftime('%a %Y-%m-%d %H:%M')} IST  "
          f"opening-range breakout on 5-minute bars (Yahoo, free, can lag)")
    print(f"Opening range 9:15-9:30: high Rs {range_high:.2f}, low Rs {range_low:.2f}")
    if triggered:
        t_str = triggered["dt"].strftime("%H:%M")
        print(f"TRIGGERED {t_str} at Rs {triggered['close']:.2f}: closed above "
              f"the range high Rs {range_high:.2f}")
        result["status"] = "triggered"
        result["trigger_time"] = t_str
        result["trigger_price"] = round(triggered["close"], 2)
    else:
        last = closed_bars[-1]
        gap = range_high - last["close"]
        print(f"WAITING  last close Rs {last['close']:.2f} "
              f"({last['dt'].strftime('%H:%M')} bar), Rs {gap:.2f} under the "
              f"range high Rs {range_high:.2f}")
        result["status"] = "waiting"
    print("Nothing was placed.")
    if args.write:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()