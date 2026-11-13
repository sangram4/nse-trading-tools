#!/usr/bin/env python3
"""
exit.py -- NSE exit planner: sets stop and target before entry (own build)
"""
import argparse
import json
import os
import sys
from datetime import datetime


def tick_round_down(price):
    if price < 250:
        tick = 0.01
    elif price < 1000:
        tick = 0.05
    else:
        tick = 0.10
    return round(price - (price % tick), 2)


def tick_round_up_half(price):
    if price < 250:
        tick = 0.01
    elif price < 1000:
        tick = 0.05
    else:
        tick = 0.10
    remainder = price % tick
    if remainder >= tick / 2:
        return round(price - remainder + tick, 2)
    return round(price - remainder, 2)


def main():
    ap = argparse.ArgumentParser(description="NSE exit planner (own build)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--symbol")
    plan.add_argument("--entry", type=float)
    plan.add_argument("--or-high", type=float, dest="or_high")
    plan.add_argument("--or-low", type=float, dest="or_low")
    plan.add_argument("--stop", default="or-mid")
    plan.add_argument("--target", default="2R")
    plan.add_argument("--entry-file", default="trader/entry.json")
    plan.add_argument("--write", action="store_true")
    plan.add_argument("--out", default="trader/plan.json")
    args = ap.parse_args()

    symbol = args.symbol
    entry = args.entry
    or_high = args.or_high
    or_low = args.or_low

    if entry is None and os.path.exists(args.entry_file):
        with open(args.entry_file) as f:
            e = json.load(f)
        if e.get("status") != "triggered":
            print(f"exit.py: {args.entry_file} has not triggered.", file=sys.stderr)
            sys.exit(1)
        symbol = symbol or e["symbol"]
        entry = e["trigger_price"]
        or_high = or_high if or_high is not None else e["range_high"]
        or_low = or_low if or_low is not None else e["range_low"]

    if entry is None or symbol is None:
        print("exit.py: need --symbol and --entry (or a triggered trader/entry.json)", file=sys.stderr)
        sys.exit(1)

    if args.stop == "or-mid":
        if or_high is None or or_low is None:
            print("exit.py: --stop or-mid needs --or-high and --or-low", file=sys.stderr)
            sys.exit(1)
        raw_stop = (or_high + or_low) / 2
        stop_label = f"opening-range midpoint: ({or_high} + {or_low}) / 2 = {raw_stop:.2f}, rounded down"
    elif args.stop == "or-low":
        raw_stop = or_low
        stop_label = "opening-range low"
    elif args.stop.startswith("price:"):
        raw_stop = float(args.stop.split(":")[1])
        stop_label = "fixed price"
    elif args.stop.startswith("pct:"):
        pct = float(args.stop.split(":")[1])
        raw_stop = entry * (1 - pct / 100)
        stop_label = f"{pct}% under the entry"
    else:
        print(f"exit.py: unknown --stop {args.stop}", file=sys.stderr)
        sys.exit(1)

    stop = tick_round_down(raw_stop)
    if stop >= entry:
        print(f"exit.py: refused -- stop Rs {stop:.2f} is at or above the entry Rs {entry:.2f}", file=sys.stderr)
        sys.exit(1)

    risk = entry - stop
    if risk / entry * 100 < 0.05:
        print(f"exit.py: refused -- risk Rs {risk:.2f} too tight", file=sys.stderr)
        sys.exit(1)

    if args.target.upper().endswith("R"):
        r_mult = float(args.target[:-1])
        raw_target = entry + r_mult * risk
        target_label = f"{r_mult}R ({r_mult} times the risk)"
    elif args.target.startswith("price:"):
        raw_target = float(args.target.split(":")[1])
        r_mult = (raw_target - entry) / risk if risk else 0
        target_label = "fixed price"
    else:
        print(f"exit.py: unknown --target {args.target}", file=sys.stderr)
        sys.exit(1)

    target = tick_round_up_half(raw_target)
    if target <= entry:
        print(f"exit.py: refused -- target Rs {target:.2f} is at or below the entry", file=sys.stderr)
        sys.exit(1)

    reward_risk = round((target - entry) / risk, 2) if risk else 0
    cost_pct = 0.083
    gain_pct = (target - entry) / entry * 100
    if gain_pct < cost_pct * 1.1:
        print(f"exit.py: refused -- target gain {gain_pct:.3f}% cannot cover the ~{cost_pct}% round-trip cost", file=sys.stderr)
        sys.exit(1)

    result = {"symbol": symbol, "date": datetime.now().strftime("%Y-%m-%d"),
              "entry": round(entry, 2), "stop": stop, "stop_label": stop_label,
              "target": target, "target_label": target_label,
              "risk_per_share": round(risk, 2), "reward_risk": reward_risk, "flat_by": "15:10"}

    print(f"Exit plan: {symbol} long")
    print(f"  Entry         Rs {entry:.2f}")
    print(f"  Stop          Rs {stop:.2f}  {stop_label}")
    print(f"  Target        Rs {target:.2f}  {target_label}")
    print(f"  Risk a share  Rs {risk:.2f} ({risk/entry*100:.2f}% of entry)")
    print(f"  Reward:risk   {reward_risk}")
    print("A stop is a plan, not a guarantee: a gap or fast market can fill past it.")

    if args.write:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()