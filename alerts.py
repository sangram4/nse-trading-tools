#!/usr/bin/env python3
"""
alerts.py -- price alerts for stop, target and flat-by time (own build)

Checks trader/plan.json (or trader/orders.json) against the symbol's
current price and says how close it is to the stop, the target, or the
flat-by time. Prints only -- it never sends anything anywhere.

Usage:
  python3 alerts.py
  python3 alerts.py --now "2026-11-09 14:50"
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)


def fetch_last_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?range=1d&interval=1m"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        return None, str(e)
    try:
        result = data["chart"]["result"][0]
        price = result["meta"].get("regularMarketPrice")
        if price is None:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
            price = closes[-1] if closes else None
    except (KeyError, IndexError, TypeError):
        return None, "no data in response"
    if price is None:
        return None, "no price found"
    return round(price, 2), None


def main():
    ap = argparse.ArgumentParser(description="Price alerts for stop/target/flat-by (own build)")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--now", help='pretend it is this IST time, e.g. "2026-11-09 14:50"')
    ap.add_argument("--near-pct", type=float, default=0.3,
                     help="flag as NEAR when within this %% of the stop or target")
    args = ap.parse_args()

    if not os.path.exists(args.plan):
        print(f"alerts.py: no plan at {args.plan}. Run exit.py plan first.", file=sys.stderr)
        sys.exit(1)

    with open(args.plan) as f:
        plan = json.load(f)

    symbol = plan["symbol"]
    stop = plan["stop"]
    target = plan["target"]
    flat_by = plan.get("flat_by", "15:10")

    price, err = fetch_last_price(symbol)
    if price is None:
        print(f"alerts.py: could not fetch {symbol}: {err}", file=sys.stderr)
        sys.exit(1)

    if args.now:
        now = datetime.strptime(args.now, "%Y-%m-%d %H:%M")
    else:
        now = datetime.utcnow() + IST_OFFSET

    fb_h, fb_m = [int(x) for x in flat_by.split(":")]
    minutes_to_flat = (fb_h * 60 + fb_m) - (now.hour * 60 + now.minute)

    print(f"{symbol}  last price Rs {price:.2f}  (checked {now.strftime('%Y-%m-%d %H:%M')} IST)")
    print(f"  stop {stop}  target {target}  flat by {flat_by}")
    print()

    dist_to_stop_pct = (price - stop) / price * 100
    dist_to_target_pct = (target - price) / price * 100

    if price <= stop:
        print(f"  ALERT: price is AT OR BELOW the stop (Rs {stop}).")
    elif dist_to_stop_pct <= args.near_pct:
        print(f"  NEAR STOP: only {dist_to_stop_pct:.2f}% above the stop (Rs {stop}).")
    else:
        print(f"  {dist_to_stop_pct:.2f}% above the stop (Rs {stop}). No alert.")

    if price >= target:
        print(f"  ALERT: price is AT OR ABOVE the target (Rs {target}).")
    elif dist_to_target_pct <= args.near_pct:
        print(f"  NEAR TARGET: only {dist_to_target_pct:.2f}% below the target (Rs {target}).")
    else:
        print(f"  {dist_to_target_pct:.2f}% below the target (Rs {target}). No alert.")

    if minutes_to_flat <= 0:
        print(f"  ALERT: past the flat-by time ({flat_by}). Should already be out.")
    elif minutes_to_flat <= 15:
        print(f"  ALERT: only {minutes_to_flat} minutes left before flat-by ({flat_by}).")
    else:
        print(f"  {minutes_to_flat} minutes left before flat-by ({flat_by}). No alert.")

    print("\nThis only prints. It never places, cancels or changes an order.")


if __name__ == "__main__":
    main()