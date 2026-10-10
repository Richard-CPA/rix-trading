#!/usr/bin/env python3
"""RixTrade-Woche 06.-09.10.2026: Marktdaten (SPX, VIX) + Trade-Statistik."""
import urllib.request, json, datetime, statistics

def yahoo(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=25))
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(r["timestamp"]):
        day = datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
        rows.append((day, q["open"][i], q["high"][i], q["low"][i], q["close"][i]))
    return rows

print("=== MARKTDATEN ===")
for label, sym in (("SPX", "%5EGSPC"), ("VIX", "%5EVIX")):
    try:
        for day, o, h, l, c in yahoo(sym):
            if day >= "2026-10-02":
                print(f"{label} {day}  O {o:8.2f}  H {h:8.2f}  L {l:8.2f}  C {c:8.2f}  Range {h-l:6.2f}")
    except Exception as e:
        print(f"{label}: FEHLER {e}")

# Trades: (Tag, Struktur, Eröffnung, Schließung, PnL, Haltedauer in Stunden)
T = [
    ("10/6", "PCS 7800/7810",      "19:12", "20:48",  1104.00, 1.60),
    ("10/7", "PCS 7735/7745",      "16:27", "18:00",   512.00, 1.55),
    ("10/7", "PCS 7755/7765",      "13:38", "19:20",   897.00, 5.70),
    ("10/7", "CCS 7810/7820",      "19:08", "21:23",   837.00, 2.25),
    ("10/8", "PCS 7735/7745",      "12:24", "18:18",   972.00, 5.90),
    ("10/8", "PCS 7720/7730",      "19:16", "20:28",   372.00, 1.20),
    ("10/8", "PCS 7760/7770",      "16:06", "23:16", -1326.50, 7.15),
    ("10/9", "PCS 7765/7775",      "16:13", "18:30",   917.00, 2.28),
    ("10/9", "IC 7730/7740/7820/7830", "16:56", "21:51", 739.00, 4.90),
    ("10/9", "CCS 7830/7840",      "18:17", "19:09",   -56.50, 0.87),
    ("10/9", "FLY 7785/7800/7815", "18:17", "23:16",  -148.60, 4.98),
]

wins = [t for t in T if t[4] > 0]
loss = [t for t in T if t[4] <= 0]
net = sum(t[4] for t in T)
print(f"\n=== STATISTIK ===")
print(f"Trades: {len(T)}  |  Gewinner: {len(wins)}  Verlierer: {len(loss)}  |  Trefferquote {len(wins)/len(T)*100:.0f} %")
print(f"Netto: {net:+,.2f} $  |  Summe Gewinne: {sum(t[4] for t in wins):+,.2f} $  |  Summe Verluste: {sum(t[4] for t in loss):+,.2f} $")
print(f"Ø Gewinn: {statistics.mean([t[4] for t in wins]):+,.2f} $  |  Ø Verlust: {statistics.mean([t[4] for t in loss]):+,.2f} $")
print(f"Payoff: {abs(statistics.mean([t[4] for t in wins]) / statistics.mean([t[4] for t in loss])):.2f}  |  Erwartungswert pro Trade: {net/len(T):+,.2f} $")
print(f"Größter Verlust = {abs(min(t[4] for t in T))/sum(t[4] for t in wins)*100:.1f} % aller Gewinne")

print(f"\n=== PRO TAG ===")
for day in ("10/6", "10/7", "10/8", "10/9"):
    d = [t for t in T if t[0] == day]
    s = sum(t[4] for t in d)
    flag = "QUALIFIZIERT" if s >= 200 else "NICHT qualifiziert (< 200 $)"
    print(f"{day}: {len(d)} Trades, {s:+,.2f} $  -> {flag}")

print(f"\n=== HALTEDAUER ===")
print(f"Ø Gewinner: {statistics.mean([t[5] for t in wins]):.2f} h")
print(f"Ø Verlierer: {statistics.mean([t[5] for t in loss]):.2f} h")
print(f"Schließungen: {sorted(set(t[3] for t in T))}")

print(f"\n=== TIME-STOP 21:30 ===")
for t in T:
    late = t[3] > "21:30"
    print(f"{t[0]} {t[2]}->{t[3]} ({(t[5]):.2f}h) {t[1]:32s} {t[4]:+9.2f} $  {'SPAET' if late else ''}")

print(f"\n=== GLEICHZEITIGE POSITIONEN (Regel: max 1) ===")
def m(x):
    h, mi = x.split(":"); return int(h) * 60 + int(mi)
byday = {}
for t in T:
    byday.setdefault(t[0], []).append(t)
for day, ts in sorted(byday.items()):
    ts = sorted(ts, key=lambda t: m(t[2]))
    for i, a in enumerate(ts):
        for b in ts[i+1:]:
            if m(b[2]) < m(a[3]):
                print(f"{day}: {a[1] if False else a[1]} ({a[2]}-{a[3]}) überlappt mit {b[1]} ({b[2]}-{b[3]})")
    peak = 0
    for mm in range(0, 1440):
        n = sum(1 for t in ts if m(t[2]) <= mm < m(t[3]))
        peak = max(peak, n)
    print(f"{day}: max {peak} gleichzeitig offene Positionen")
