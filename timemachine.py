#!/usr/bin/env python3
"""
timemachine.py -- Monte Carlo replay of a planned trade (own build)
"""
import argparse
import json
import random
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

IST_OFFSET = timedelta(hours=5, minutes=30)


def fetch_bars(symbol, days="60d", interval="5m"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
           f"?range={days}&interval={interval}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
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


def group_by_session(bars):
    sessions = {}
    for b in bars:
        key = b["dt"].strftime("%Y-%m-%d")
        sessions.setdefault(key, []).append(b)
    return sessions


def main():
    ap = argparse.ArgumentParser(description="Monte Carlo trade replay (own build)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--plan", default="trader/plan.json")
    run.add_argument("--replays", type=int, default=10000)
    run.add_argument("--seed", type=int, default=19)
    run.add_argument("--window", type=int, default=2)
    run.add_argument("--until", default="15:10")
    args = ap.parse_args()

    with open(args.plan) as f:
        plan = json.load(f)

    symbol = plan["symbol"]
    entry = plan["entry"]
    stop = plan["stop"]
    target = plan["target"]
    risk = entry - stop

    bars, err = fetch_bars(symbol)
    if bars is None:
        print(f"timemachine.py: could not fetch {symbol}: {err}", file=sys.stderr)
        sys.exit(1)

    sessions = group_by_session(bars)
    full_sessions = []
    for date, day_bars in sessions.items():
        if date == plan.get("date"):
            continue
        day_bars.sort(key=lambda b: b["dt"])
        if len(day_bars) >= 60:
            full_sessions.append(day_bars)

    if len(full_sessions) < 20:
        print(f"timemachine.py: only {len(full_sessions)} full sessions available (need at least 20)", file=sys.stderr)
        sys.exit(1)

    ratio_by_slot = {}
    for day_bars in full_sessions:
        prev_close = day_bars[0]["open"]
        for slot, b in enumerate(day_bars):
            ratios = (b["open"] / prev_close, b["high"] / prev_close, b["low"] / prev_close, b["close"] / prev_close)
            ratio_by_slot.setdefault(slot, []).append(ratios)
            prev_close = b["close"]

    until_h, until_m = [int(x) for x in args.until.split(":")]
    n_slots = len(ratio_by_slot)
    start_minutes = 9 * 60 + 15
    until_minutes = until_h * 60 + until_m
    total_slots_to_until = (until_minutes - start_minutes) // 5

    entry_bar = plan.get("entry_bar")
    if entry_bar is None:
        entry_time = plan.get("entry_time", "10:00 AM")
        try:
            t = datetime.strptime(entry_time.upper().replace(" ", ""), "%I:%M%p")
            entry_minutes = t.hour * 60 + t.minute
            entry_bar = (entry_minutes - start_minutes) // 5
        except ValueError:
            entry_bar = 8

    replay_slots = list(range(entry_bar + 1, min(total_slots_to_until + 1, n_slots)))
    if not replay_slots:
        print("timemachine.py: no slots to replay before --until", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)
    target_first = stop_first = neither = 0
    closes_at_until = []
    r_values = []

    for _ in range(args.replays):
        price = entry
        hit = None
        for slot in replay_slots:
            lo_slot = max(0, slot - args.window)
            hi_slot = min(n_slots - 1, slot + args.window)
            candidates = []
            for s in range(lo_slot, hi_slot + 1):
                candidates.extend(ratio_by_slot.get(s, []))
            if not candidates:
                continue
            o_r, h_r, l_r, c_r = rng.choice(candidates)
            bar_high = price * (h_r / o_r)
            bar_low = price * (l_r / o_r)
            bar_close = price * (c_r / o_r)
            if bar_low <= stop and bar_high >= target:
                hit = "stop"
            elif bar_low <= stop:
                hit = "stop"
            elif bar_high >= target:
                hit = "target"
            price = bar_close
            if hit:
                break
        if hit == "target":
            target_first += 1
            r_values.append((target - entry) / risk)
        elif hit == "stop":
            stop_first += 1
            r_values.append(-1.0)
        else:
            neither += 1
            r_values.append((price - entry) / risk)
        closes_at_until.append(price)

    n = args.replays
    closes_at_until.sort()
    median = closes_at_until[n // 2]
    p5 = closes_at_until[int(n * 0.05)]
    p95 = closes_at_until[int(n * 0.95)]
    avg_r = sum(r_values) / n

    print(f"{symbol} long, entry {entry}, stop {stop}, target {target} (risk {risk:.2f} a share)")
    print(f"{n:,} replays of the rest of the session, seed {args.seed}, {len(full_sessions)} full sessions in the pool.")
    print()
    print(f"  target first   {target_first/n*100:5.1f} %")
    print(f"  stop first     {stop_first/n*100:5.1f} %")
    print(f"  neither        {neither/n*100:5.1f} %   still open at {args.until}")
    print()
    print(f"  Price at {args.until}: median {median:.2f}, 90% of replays between {p5:.2f} and {p95:.2f}.")
    print(f"  Average R: {avg_r:+.3f}")
    print()
    print("A simulation built from this stock's own recent sessions. Not a prediction. Repeat with --seed", args.seed)


if __name__ == "__main__":
    main()