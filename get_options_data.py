"""Fetch SPY options chain for 0DTE trade planning.

yfinance 1.5.2 delivers no greeks (delta/theta/vega=0) and broken IV for SPY
0DTE chains -> delta + IV are computed locally via Black-Scholes (Newton-Raphson
on the mid price). r = fed funds proxy, T = hours to 16:00 ET expiry.
"""
import math
from datetime import datetime
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas as pd

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.float_format', '{:.2f}'.format)

R = 0.045  # risk-free rate proxy


def bs_price(cp, s, k, t, sigma):
    if t <= 0 or sigma <= 0:
        return max(0.0, (s - k) if cp == 'c' else (k - s))
    d1 = (math.log(s / k) + (R + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if cp == 'c':
        return s * _N(d1) - k * math.exp(-R * t) * _N(d2)
    return k * math.exp(-R * t) * _N(-d2) - s * _N(-d1)


def _N(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def implied_vol(cp, s, k, t, mid):
    if mid <= 0 or t <= 0:
        return None
    intrinsic = max(0.0, (s - k) if cp == 'c' else (k - s))
    if mid <= intrinsic:
        return 0.001  # effectively zero time value
    lo, hi = 1e-4, 5.0
    for _ in range(100):
        sig = 0.5 * (lo + hi)
        p = bs_price(cp, s, k, t, sig)
        if p > mid:
            hi = sig
        else:
            lo = sig
        if hi - lo < 1e-6:
            break
    return 0.5 * (lo + hi)


def bs_delta(cp, s, k, t, sigma):
    if sigma <= 0:
        return 1.0 if (cp == 'c' and s > k) else (0.0 if cp == 'c' else (-1.0 if s < k else 0.0))
    d1 = (math.log(s / k) + (R + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    if cp == 'c':
        return _N(d1)
    return _N(d1) - 1.0


def hours_to_expiry(exp_str):
    # SPY-Optionen verfallen 16:00 ET (nicht UTC!)
    exp = datetime.strptime(exp_str, '%Y-%m-%d').replace(hour=16, minute=0, tzinfo=ZoneInfo('America/New_York'))
    now = datetime.now(ZoneInfo('America/New_York'))
    return max((exp - now).total_seconds() / 3600.0, 0.0)


def enrich(df, cp, spot, t):
    rows = []
    for _, r in df.iterrows():
        k = float(r['strike'])
        bid, ask = float(r['bid']), float(r['ask'])
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else None
        iv = implied_vol(cp, spot, k, t, mid) if mid else None
        delta = bs_delta(cp, spot, k, t, iv) if iv else None
        rows.append((k, bid, ask, mid, iv, delta))
    out = pd.DataFrame(rows, columns=['strike', 'bid', 'ask', 'mid', 'iv', 'delta'])
    return out


spy = yf.Ticker('SPY')

hist = spy.history(period='2d')
spot = hist['Close'].iloc[-1] if not hist.empty else None
print(f"SPY current: ~${spot:.2f}" if spot else "SPY: N/A")

expirations = list(spy.options)
print(f"\nAvailable expirations ({len(expirations)} total):")
for e in expirations[:8]:
    print(f"  {e}")

today_exp = expirations[0]
t_hours = hours_to_expiry(today_exp)
t = t_hours / 8760.0  # BS expects years
print(f"\n{'='*80}")
print(f"CHAIN FOR: {today_exp} (0DTE, {t_hours:.1f}h to expiry, BS-greeks)")
print('='*80)

opt = spy.option_chain(today_exp)
strike_min, strike_max = round(spot) - 30, round(spot) + 20

print(f"\n--- CALLS (delta/IV computed via Black-Scholes) ---")
calls_f = enrich(opt.calls, 'c', spot, t)
calls_f = calls_f[(calls_f['strike'] >= strike_min) & (calls_f['strike'] <= strike_max)]
for _, r in calls_f.iterrows():
    iv = r['iv'] or 0
    d = r['delta'] or 0
    m = r['mid'] if r['mid'] is not None else 0
    print(f"  {r['strike']:6.1f} | bid={r['bid']:5.2f} ask={r['ask']:5.2f} mid={m:5.2f} IV={iv:.1%} delta={d:.2f}")

print(f"\n--- PUTS (delta/IV computed via Black-Scholes) ---")
puts_f = enrich(opt.puts, 'p', spot, t)
puts_f = puts_f[(puts_f['strike'] >= strike_min) & (puts_f['strike'] <= strike_max)]
for _, r in puts_f.iterrows():
    iv = r['iv'] or 0
    d = r['delta'] or 0
    m = r['mid'] if r['mid'] is not None else 0
    print(f"  {r['strike']:6.1f} | bid={r['bid']:5.2f} ask={r['ask']:5.2f} mid={m:5.2f} IV={iv:.1%} delta={d:.2f}")

# ATM straddle / 1-sigma move
atm = round(spot)
c_atm = calls_f[calls_f['strike'] == atm]
p_atm = puts_f[puts_f['strike'] == atm]
if not c_atm.empty and not p_atm.empty:
    strad = (c_atm.iloc[0]['mid'] or 0) + (p_atm.iloc[0]['mid'] or 0)
    print(f"\nATM straddle {atm}: {strad:.2f} -> 1-sigma range approx {spot-strad:.2f} .. {spot+strad:.2f}")

# IV comparison with next expiry
if len(expirations) >= 2:
    next_exp = expirations[1]
    t2 = hours_to_expiry(next_exp)
    print(f"\n{'='*80}")
    print(f"CHAIN FOR: {next_exp} (next expiry, {t2:.0f}h)")
    print('='*80)
    opt2 = spy.option_chain(next_exp)
    atm2 = round(spot)
    for exp_label, opt_chain, tt_h in [(today_exp, opt, t_hours), (next_exp, opt2, t2)]:
        tt = tt_h / 8760.0
        ce = enrich(opt_chain.calls, 'c', spot, tt)
        pe = enrich(opt_chain.puts, 'p', spot, tt)
        cc = ce[ce['strike'] == atm2]
        pp = pe[pe['strike'] == atm2]
        if not cc.empty and not pp.empty:
            cm, pm = cc.iloc[0]['mid'], pp.iloc[0]['mid']
            if cm is not None and pm is not None:
                print(f"  ATM {atm2} {exp_label}: C mid={cm:.2f} IV={cc.iloc[0]['iv']:.1%} | P mid={pm:.2f} IV={pp.iloc[0]['iv']:.1%}")
