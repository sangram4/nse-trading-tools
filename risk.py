#!/usr/bin/env python3
"""
risk.py -- checks proposed orders against configured limits (own build)
"""
import argparse
import json
import os
import sys
from datetime import datetime


def main():
    ap = argparse.ArgumentParser(description="Risk checker (own build)")
    ap.add_argument("--orders", default="trader/orders.json")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--now", help='pretend it is this IST time, e.g. "2026-11-09 10:00"')
    args = ap.parse_args()

    with open(args.orders) as f:
        data = json.load(f)
    orders = data.get("orders", [])

    config = {}
    if os.path.exists(args.config):
        with open(args.config) as f:
            config = json.load(f)

    max_loss_per_trade = config.get("max_loss_per_trade_usd", float("inf"))
    min_reward_risk = config.get("min_reward_risk", 1.0)
    no_entries_before = config.get("no_entries_before", "09:35")
    no_entries_after = config.get("no_entries_after", "15:00")

    if args.now:
        now = datetime.strptime(args.now, "%Y-%m-%d %H:%M")
    else:
        now = datetime.now()

    nb_h, nb_m = [int(x) for x in no_entries_before.split(":")]
    na_h, na_m = [int(x) for x in no_entries_after.split(":")]
    now_minutes = now.hour * 60 + now.minute
    window_ok = (nb_h * 60 + nb_m) <= now_minutes <= (na_h * 60 + na_m)

    passed = blocked = 0
    for o in orders:
        risk_per_share = o["entry"] - o["stop"]
        reward_risk = (o["target"] - o["entry"]) / risk_per_share if risk_per_share else 0
        reasons = []
        if o["max_loss"] > max_loss_per_trade:
            reasons.append(f"max loss Rs {o['max_loss']} over limit Rs {max_loss_per_trade}")
        if reward_risk < min_reward_risk:
            reasons.append(f"reward:risk {reward_risk:.2f} under minimum {min_reward_risk}")
        if not window_ok:
            reasons.append(f"outside the entry window ({no_entries_before}-{no_entries_after} IST)")

        if reasons:
            blocked += 1
            print(f"BLOCK  {o['side']} {o['symbol']} {o['shares']} shares: " + "; ".join(reasons))
        else:
            passed += 1
            print(f"PASS   {o['side']} {o['symbol']} {o['shares']} shares, entry {o['entry']}, stop {o['stop']}, target {o['target']}: max loss Rs {o['max_loss']} (limit Rs {max_loss_per_trade}), reward:risk {reward_risk:.2f} (min {min_reward_risk})")

    print()
    print(f"{passed} passed, {blocked} blocked at {now.strftime('%Y-%m-%d %H:%M')}.")
    if blocked:
        print("Blocked orders do not go to a broker. Fix the order or your rules, then check again.")


if __name__ == "__main__":
    main()