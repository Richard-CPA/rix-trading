#!/usr/bin/env python3
"""
rix-trading Trade Log — OptionsFunding Growth 100K Evaluation

Pflegt TRADE_LOG.yaml und trackt die Eval-Regeln automatisch:
  - Profit Target:  $12.000 (12%)
  - Trailing DD:    $6.000 (End of Day)
  - Consistency:    Bester Gewinntag <= 30% aller Gewinntage

Befehle:
  status                    Zeigt aktuellen Eval-Status (kum. P&L, Consistency, DD, Rest zum Target)
  add   ...                 Neuen Trade hinzufügen (berechnet P&L pro Leg + net_pnl)
  check [--day-size N]      Wie viele weitere Gewinntage à N braucht es fuer <30%?

Beispiel add:
  python3 trade_log.py add \
    --date 2026-08-04 --type bull_put_credit_spread --expiry 2026-08-04 --dte 0 \
    --legs "short:744:put:12:1.04:2.17;long:741:put:12:0.46:1.11" \
    --fees 31.20 --open 09:36 --close 09:40 \
    --note "ATM strikes at open — managed loss"
"""

import argparse
import argparse
import math
import sys
from pathlib import Path

# Pipe-robust (z.B. `trade_log.py status | head`): BrokenPipeError still beenden
try:
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (ImportError, AttributeError, ValueError):
    pass

try:
    import yaml
except ImportError:
    sys.exit("pyyaml fehlt. Nutze: /opt/data/.venv-bt/bin/python trade_log.py")

LOG_PATH = Path(__file__).parent / "TRADE_LOG.yaml"
START_BALANCE = 100_000.0
TARGET = 12_000.0
DD_LIMIT = 6_000.0
CONSISTENCY_CAP = 0.30

HEADER = """# SPY Trade Log — rix-trading
# OptionsFunding Growth 100K Evaluation
# Format: YAML (gepflegt via trade_log.py — nicht manuell editieren)
"""

# Globaler Log-Pfad (überschreibbar via --log, z.B. für Tests)
LOG_PATH_OVERRIDE = None


def load_log() -> dict:
    path = LOG_PATH_OVERRIDE or LOG_PATH
    if not path.exists():
        return {"trades": []}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"trades": []}


def save_log(data: dict) -> None:
    path = LOG_PATH_OVERRIDE or LOG_PATH
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=100)


def compute_stats(trades: list) -> dict:
    """Berechnet Eval-Kennzahlen aus den Trades (single source of truth)."""
    cumulative = sum(t.get("net_pnl", 0.0) for t in trades)
    winning_days = [t for t in trades if t.get("net_pnl", 0) > 0]
    losing_days = [t for t in trades if t.get("net_pnl", 0) < 0]
    win_sum = sum(t["net_pnl"] for t in winning_days)
    best_day = max((t["net_pnl"] for t in winning_days), default=0.0)

    # Trailing Drawdown: Startbalance + kum. P&L, Floor = höchster bisheriger Stand
    balance = START_BALANCE + cumulative
    peak = START_BALANCE + max(0.0, max((t.get("cum_after", 0.0) for t in trades), default=0.0))
    # cum_after existiert nicht im Log → Peak aus laufender Summe
    running = START_BALANCE
    peak = START_BALANCE
    for t in trades:
        running += t.get("net_pnl", 0.0)
        peak = max(peak, running)
    drawdown = peak - balance

    consistency = (best_day / win_sum) if win_sum > 0 else None
    return {
        "cumulative": cumulative,
        "balance": balance,
        "peak": peak,
        "drawdown": drawdown,
        "winning_days": len(winning_days),
        "losing_days": len(losing_days),
        "win_sum": win_sum,
        "best_day": best_day,
        "consistency": consistency,  # None wenn keine Gewinntage
        "remaining": TARGET - cumulative,
    }


def cmd_status(args) -> int:
    data = load_log()
    trades = data.get("trades", [])
    s = compute_stats(trades)

    print("=" * 58)
    print("RIX TRADING — OptionsFunding Growth 100K Evaluation")
    print("=" * 58)
    print(f"Trades gesamt:      {len(trades)}  ({s['winning_days']} gewonnen / {s['losing_days']} verloren)")
    print(f"Kum. P&L:           ${s['cumulative']:,.2f}")
    print(f"Kontostand:         ${s['balance']:,.2f}")
    print(f"Target ($12.000):   ${s['remaining']:,.2f} fehlen  ({max(0, s['remaining']/TARGET*100):.0f}%)")
    dd_used = s["drawdown"] / DD_LIMIT * 100
    print(f"Trailing DD:        ${s['drawdown']:,.2f} von $6.000 ({dd_used:.0f}% genutzt)")
    print("-" * 58)

    # Consistency-Check
    if s["consistency"] is None:
        print("Consistency:        n/a (noch kein Gewinntag)")
    else:
        ok = s["consistency"] <= CONSISTENCY_CAP
        status = "OK" if ok else "ZU HOCH"
        print(f"Consistency:        {s['consistency']*100:.1f}%  (Cap 30%) → {status}")
        if not ok:
            needed = s["best_day"] / CONSISTENCY_CAP - s["win_sum"]
            print(f"  -> braucht noch ~${needed:,.0f} Gewinn-Summe (winning days) fuer <30%")

    print("=" * 58)
    print(f"{'#':>3}  {'Datum':<12} {'Typ':<26} {'P&L':>10}")
    print("-" * 58)
    for t in trades:
        typ = t.get("type", "?")
        typ = typ[:26]
        print(f"{t.get('id','?'):>3}  {t.get('date','?'):<12} {typ:<26} ${t.get('net_pnl',0):>9,.2f}")
    print("=" * 58)
    return 0


def parse_legs(legs_str: str) -> list:
    """Format: side:strike:type:qty:avg_open:avg_close (mehrere mit ; getrennt)
    short:744:put:12:1.04:2.17  →  P&L = (1.04 - 2.17) * 12 * 100 = -1356
    long:741:put:12:0.46:1.11   →  P&L = (1.11 - 0.46) * 12 * 100 = +780
    """
    legs = []
    for part in legs_str.split(";"):
        fields = part.strip().split(":")
        if len(fields) != 6:
            sys.exit(f"Leg-Format falsch: '{part}' — erwartet side:strike:type:qty:open:close")
        side, strike, otype, qty, avg_open, avg_close = fields
        qty = int(qty)
        avg_open, avg_close = float(avg_open), float(avg_close)
        if side == "short":
            pnl = (avg_open - avg_close) * qty * 100
        elif side == "long":
            pnl = (avg_close - avg_open) * qty * 100
        else:
            sys.exit(f"side muss 'short' oder 'long' sein, war '{side}'")
        legs.append({
            "side": side, "strike": int(float(strike)), "type": otype,
            "qty": qty, "avg_open": avg_open, "avg_close": avg_close,
            "pnl": round(pnl, 2),
        })
    return legs


def cmd_add(args) -> int:
    data = load_log()
    trades = data.get("trades", [])
    new_id = max((t.get("id", 0) for t in trades), default=0) + 1

    legs = parse_legs(args.legs)
    gross = sum(l["pnl"] for l in legs)
    net = round(gross - args.fees, 2)

    trade = {
        "id": new_id,
        "date": args.date,
        "type": args.type,
        "underlying": args.underlying or "SPY",
        "expiry": args.expiry,
        "dte": args.dte,
        "legs": legs,
        "total_fees": args.fees,
        "net_pnl": net,
        "times": {"open": f"{args.date} {args.open} ET", "close": f"{args.date} {args.close} ET"},
        "market_context": {"note": args.note} if args.note else {},
    }
    if args.lessons:
        trade["lessons"] = [l.strip() for l in args.lessons.split("|") if l.strip()]

    trades.append(trade)
    data["trades"] = trades

    # progress-Sektion neu berechnen
    s = compute_stats(trades)
    consistency_note = None
    if s["consistency"] is not None:
        if s["consistency"] <= CONSISTENCY_CAP:
            consistency_note = f"OK: Best day ${s['best_day']:,.0f} / ${s['win_sum']:,.0f} = {s['consistency']*100:.0f}%"
        else:
            needed = s["best_day"] / CONSISTENCY_CAP - s["win_sum"]
            consistency_note = (f"ZU HOCH: Best day ${s['best_day']:,.0f} / ${s['win_sum']:,.0f} = "
                                f"{s['consistency']*100:.0f}% — braucht ~${needed:,.0f} weitere Gewinn-Summe")
    data["progress"] = {
        "cumulative_pnl": round(s["cumulative"], 2),
        "target": TARGET,
        "balance": round(s["balance"], 2),
        "trailing_dd": round(s["drawdown"], 2),
        "winning_days": s["winning_days"],
        "losing_days": s["losing_days"],
        "consistency_pct": round(s["consistency"] * 100, 1) if s["consistency"] is not None else None,
        "consistency_note": consistency_note,
    }
    save_log(data)

    print(f"✅ Trade #{new_id} geloggt: {args.date} {args.type} — net_pnl ${net:,.2f}")
    if s["consistency"] is not None:
        print(f"   Kumuliert: ${s['cumulative']:,.2f} | Consistency: {s['consistency']*100:.1f}%")
    else:
        print(f"   Kumuliert: ${s['cumulative']:,.2f}")
    return 0


def cmd_check(args) -> int:
    """Simuliert: Wie viele weitere Gewinntage à X braucht es, um unter 30% zu kommen?"""
    data = load_log()
    s = compute_stats(data.get("trades", []))
    day_size = args.day_size

    if s["consistency"] is None:
        print("Noch kein Gewinntag — jede weitere Serie zählt ab jetzt.")
        return 0

    print(f"Aktuell: Best day ${s['best_day']:,.0f} / Win-Summe ${s['win_sum']:,.0f} = "
          f"{s['consistency']*100:.1f}% (Cap 30%)")
    print(f"Simulation mit {day_size} pro weiterem Gewinntag:")
    print(f"{'Tage':>5} {'Neue Win-Summe':>16} {'Ratio':>8} {'Status':>10}")
    needed = s["best_day"] / CONSISTENCY_CAP - s["win_sum"]
    import math
    days_needed = max(0, math.ceil(needed / day_size))
    for n in range(0, days_needed + 3):
        win_sum = s["win_sum"] + n * day_size
        ratio = s["best_day"] / win_sum if win_sum else 0
        ok = ratio <= CONSISTENCY_CAP
        print(f"{n:>5} {win_sum:>16,.0f} {ratio*100:>7.1f}% {'✅' if ok else '❌':>10}")
    print(f"\n→ Bei ${day_size:,.0f}/Tag: {days_needed} weitere Gewinntage noetig "
          f"(kum. Gewinn dann ${s['win_sum'] + days_needed*day_size:,.0f}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="rix-trading Trade Log (OptionsFunding 100K Eval)")
    parser.add_argument("--log", help="Alternativer Pfad zur TRADE_LOG.yaml (fuer Tests)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Eval-Status anzeigen")

    p_add = sub.add_parser("add", help="Trade hinzufuegen")
    p_add.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_add.add_argument("--type", required=True, help="z.B. bull_put_credit_spread, iron_condor")
    p_add.add_argument("--expiry", required=True, help="YYYY-MM-DD")
    p_add.add_argument("--dte", type=int, required=True)
    p_add.add_argument("--underlying", default="SPY")
    p_add.add_argument("--legs", required=True,
                       help="short:strike:put:qty:open:close;long:strike:put:qty:open:close")
    p_add.add_argument("--fees", type=float, required=True)
    p_add.add_argument("--open", required=True, help="HH:MM ET")
    p_add.add_argument("--close", required=True, help="HH:MM ET")
    p_add.add_argument("--note", default="")
    p_add.add_argument("--lessons", default="", help="mit | getrennte Lessons")

    p_check = sub.add_parser("check", help="Consistency-Simulation")
    p_check.add_argument("--day-size", type=float, default=1000.0)

    args = parser.parse_args()
    if args.log:
        global LOG_PATH_OVERRIDE
        LOG_PATH_OVERRIDE = Path(args.log)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "check":
        return cmd_check(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
