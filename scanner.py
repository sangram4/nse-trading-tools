#!/usr/bin/env python3
"""
scanner.py -- NSE daily chart scanner (own build, stdlib only)
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime


def fetch_daily_closes(symbol, days=60):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
           f"?range={days}d&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        return None, str(e)
    try:
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return None, "no data in response"
    out = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
        out.append((d, round(c, 2)))
    return out, None


def rsi14(closes):
    n = len(closes)
    rsis = [None] * n
    if n < 15:
        return rsis
    gains, losses = [], []
    for i in range(1, 15):
        chg = closes[i] - closes[i - 1]
        gains.append(max(chg, 0))
        losses.append(max(-chg, 0))
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    rsis[14] = 100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss else 100.0
    for i in range(15, n):
        chg = closes[i] - closes[i - 1]
        gain = max(chg, 0)
        loss = max(-chg, 0)
        avg_gain = (avg_gain * 13 + gain) / 14
        avg_loss = (avg_loss * 13 + loss) / 14
        rsis[i] = 100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss else 100.0
    return rsis


def check_setups(closes):
    vals = [c for _, c in closes]
    n = len(vals)
    hits = []
    if n < 21:
        return hits
    last = vals[-1]
    window = vals[-21:-1]
    if last > max(window):
        hits.append("breakout_20d")
    if n >= 16:
        seg_start = vals[-16]
        seg_end = vals[-6]
        if seg_start > 0 and (seg_end / seg_start - 1) * 100 > 10:
            last5 = vals[-5:]
            if (max(last5) - min(last5)) / min(last5) * 100 <= 5:
                hits.append("bull_flag")
    if n >= 22:
        ma20_prev = sum(vals[-22:-2]) / 20
        ma20_now = sum(vals[-21:-1]) / 20
        prev_close = vals[-2]
        if prev_close < ma20_prev and last > ma20_now:
            hits.append("reclaim_ma20")
    rsis = rsi14(vals)
    if rsis[-1] is not None:
        if rsis[-1] < 30:
            hits.append("oversold")
        if len(rsis) >= 2 and rsis[-2] is not None and rsis[-2] < 30 and last > vals[-2]:
            hits.append("oversold_bounce")
    return hits


def main():
    ap = argparse.ArgumentParser(description="NSE daily chart scanner (own build)")
    ap.add_argument("--symbols", help="comma-separated NSE symbols, e.g. RELIANCE,TCS")
    ap.add_argument("--file", help="file with one symbol per line")
    ap.add_argument("--min-price", type=float, default=20.0)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default="trader/watchlist.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    symbols = []
    if args.symbols:
        symbols += [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.file:
        with open(args.file) as f:
            symbols += [line.strip().upper() for line in f if line.strip()]
    if not symbols:
        print("scanner.py: no symbols given.", file=sys.stderr)
        sys.exit(1)
    hits = []
    scanned = 0
    failed = []
    for sym in symbols:
        closes, err = fetch_daily_closes(sym)
        if closes is None:
            failed.append(sym)
            continue
        if not closes or closes[-1][1] < args.min_price:
            continue
        scanned += 1
        setups = check_setups(closes)
        if setups:
            last_date, last_close = closes[-1]
            hits.append({"symbol": sym, "close": last_close, "as_of": last_date, "setups": setups})
        time.sleep(0.3)
    result = {"mode": "daily", "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "requested": len(symbols), "scanned": scanned, "failed": failed, "hits": hits}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Daily scan: {len(symbols)} symbols requested, {scanned} scanned, "
              f"{len(failed)} failed, {len(hits)} matched a setup.")
        if failed:
            print(f"  failed: {', '.join(failed)}")
        for h in hits:
            print(f"  {h['symbol']:<12} Rs {h['close']:<10} {', '.join(h['setups'])}")
        print("A scan is a list of charts that match a rule, not a list of stocks to buy.")
    if args.write:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()