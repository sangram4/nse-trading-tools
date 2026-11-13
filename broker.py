#!/usr/bin/env python3
"""
broker.py -- order tickets and your yes, never places anything (own build)

This tool never talks to a broker. It shows the ticket, checks that
risk.py passed this exact order today, and records your explicit yes.
Placing the order (calling a broker API) is a separate, deliberate step
you take yourself, outside this script.

Usage:
  python3 broker.py show
  python3 broker.py approve --reply "yes"
  python3 broker.py decline
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

ORDERS = "trader/orders.json"
RISK = "trader/state/risk.json"
CONFIG = "trader/config.json"
STATE = "trader/state/broker.json"


def fingerprint(order):
    core = {k: order[k] for k in ("symbol", "side", "shares", "entry", "stop", "target") if k in order}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def status_of(order, risk, state, today):
    fp = fingerprint(order)
    if not risk or risk.get("date") != today:
        return False, "NOT READY: risk.py has not checked this order today"
    rv = next((r for r in risk.get("results", []) if r["fingerprint"] == fp), None)
    if rv is None:
        return False, "NOT READY: this exact order was not in today's risk check"
    if rv["verdict"] != "PASS":
        return False, "BLOCKED by risk.py: " + "; ".join(rv.get("reasons", []))
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and rec.get("date") == today:
            return False, f"ALREADY {rec['status']} at {rec['at']}"
    return True, "READY: risk.py PASS, waiting for your yes"


def parse_yes(reply):
    raw = (reply or "").strip().lower()
    if not raw or "?" in raw:
        return False, "empty or a question, not a yes"
    words = raw.split()
    if words[0] != "yes":
        return False, "only a reply starting with \"yes\" counts"
    doubt = {"no", "not", "wait", "cancel", "maybe", "unless", "if"}
    if doubt & set(words[1:]):
        return False, "the reply has a condition or doubt in it"
    return True, "explicit yes"


def main():
    ap = argparse.ArgumentParser(description="Order ticket and your yes (own build). Never places orders.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p = sub.add_parser("approve")
    p.add_argument("--reply", required=True)
    sub.add_parser("decline")
    args = ap.parse_args()

    order = load_json(ORDERS, {}).get("orders", [{}])[0]
    if not order:
        print("broker.py: no order in trader/orders.json. Run budget.py first.", file=sys.stderr)
        sys.exit(1)
    risk = load_json(RISK)
    state = load_json(STATE, {"orders": []})
    config = load_json(CONFIG, {})
    today = datetime.now().strftime("%Y-%m-%d")
    ready, label = status_of(order, risk, state, today)
    paper = config.get("paper", True)

    if args.cmd == "show":
        acct = "DRY RUN (paper mode: nothing would be sent)" if paper else "LIVE ACCOUNT, REAL MONEY"
        print(f"ORDER  {acct}")
        print(f"  {order['side'].upper()} {order['shares']} {order['symbol']}, "
              f"entry {order['entry']}, stop {order['stop']}, target {order['target']}")
        print(f"  max loss Rs {order.get('max_loss')}")
        print(f"  {label}")
        if ready:
            print("  Reply \"yes\" to approve this one order, or \"no\" to skip it.")
            print("  Even then, nothing is placed automatically -- that is a separate,")
            print("  deliberate step through your own broker connection.")
        sys.exit(0 if ready else 1)

    elif args.cmd == "approve":
        if not ready:
            print(f"broker.py: order is not ready: {label}", file=sys.stderr)
            sys.exit(1)
        ok, why = parse_yes(args.reply)
        if not ok:
            print(f"Not recorded: {why}.")
            sys.exit(1)
        state.setdefault("orders", []).append({
            "fingerprint": fingerprint(order), "date": today,
            "at": datetime.now().isoformat(), "status": "approved", "reply": args.reply,
            "symbol": order["symbol"], "plain": f"{order['side']} {order['shares']} {order['symbol']}",
        })
        os.makedirs("trader/state", exist_ok=True)
        with open(STATE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"Recorded your yes for {order['symbol']}.")
        print("This script still has NOT placed anything. If you want to actually send this")
        print("order, that happens through your own broker's API/app, as a separate step you")
        print("take deliberately -- never automatically from this approval.")

    elif args.cmd == "decline":
        state.setdefault("orders", []).append({
            "fingerprint": fingerprint(order), "date": today,
            "at": datetime.now().isoformat(), "status": "declined",
            "symbol": order["symbol"],
        })
        os.makedirs("trader/state", exist_ok=True)
        with open(STATE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"Recorded: declined. Nothing was sent.")


if __name__ == "__main__":
    main()