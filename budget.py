#!/usr/bin/env python3
"""
budget.py -- position sizer (own build)
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(description="Position sizer (own build)")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--budget", type=float, help="override budget in config")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default="trader/orders.json")
    args = ap.parse_args()

    with open(args.plan) as f:
        plan = json.load(f)

    config = {}
    if os.path.exists(args.config):
        with open(args.config) as f:
            config = json.load(f)

    budget = args.budget if args.budget is not None else config.get("budget")
    if budget is None:
        print("budget.py: no budget. Pass --budget or set \"budget\" in config.json", file=sys.stderr)
        sys.exit(1)

    cash_buffer_pct = config.get("cash_buffer_pct", 10)
    max_position_pct = config.get("max_position_pct", 75)
    max_order_usd = config.get("max_order_usd", budget * 0.8)
    max_loss_per_trade = config.get("max_loss_per_trade_usd", budget * 0.01)

    entry = plan["entry"]
    stop = plan["stop"]
    target = plan["target"]
    risk_per_share = entry - stop

    limits = {
        "max loss": int(max_loss_per_trade / risk_per_share),
        "position cap": int((max_position_pct / 100 * budget) / entry),
        "max order": int(max_order_usd / entry),
        "cash": int((budget * (1 - cash_buffer_pct / 100)) / entry),
    }

    shares = min(limits.values())
    binding = min(limits, key=limits.get)

    if shares <= 0:
        print("budget.py: sized to 0 shares", file=sys.stderr)
        sys.exit(1)

    cost = round(shares * entry, 2)
    max_loss = round(shares * risk_per_share, 2)

    print(f"{plan['symbol']} buy, entry {entry}")
    print(f"Stop {stop}, target {target}. Risk {risk_per_share:.2f} a share.")
    print()
    for name, n in limits.items():
        marker = "  <- binds" if name == binding else ""
        print(f"  {name:<13} {n} shares{marker}")
    print()
    print(f"Size: {shares} shares of {plan['symbol']} = Rs {cost} at {entry}. Max loss at the stop: {shares} x {risk_per_share:.2f} = Rs {max_loss}")

    order = {"symbol": plan["symbol"], "side": "buy", "shares": shares, "entry": entry,
             "stop": stop, "target": target, "cost": cost, "max_loss": max_loss}

    if args.write:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump({"orders": [order]}, f, indent=2)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()