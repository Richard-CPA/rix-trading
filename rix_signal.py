#!/usr/bin/env python3
"""Rix Signal — strukturiertes Pre-Market Signal-JSON für AI-Entscheidungen.

Sammelt SPY-Spot, VIX, Options-Chain (CBOE), GEX-Walls, technische Levels
und gibt alles als maschinenlesbares JSON aus → wird in den AI-Prompt injiziert.

Usage:
    cd /opt/data/rix-trading && source .venv/bin/activate && python rix_signal.py
"""

import json
import math
import statistics
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
import rix_compat as yf  # RixTrade zuerst, yfinance nur als Rueckfall
import numpy as np

# ─── Konstanten ────────────────────────────────────────────────────────────
RATE = 0.045  # risikofreier Zins (Fed Funds proxy)
CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/SPY.json"
SPY_TICKER = "SPY"
VIX_TICKER = "^VIX"

ET = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
UTC = timezone.utc


# ─── Black-Scholes-Hilfsfunktionen ─────────────────────────────────────────
def bs_price(cp, s, k, t, sigma):
    if t <= 0 or sigma <= 0:
        return max(0.0, (s - k) if cp == 'c' else (k - s))
    d1 = (math.log(s / k) + (RATE + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if cp == 'c':
        return s * _N(d1) - k * math.exp(-RATE * t) * _N(d2)
    return k * math.exp(-RATE * t) * _N(-d2) - s * _N(-d1)


def _N(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def implied_vol(cp, s, k, t, mid):
    if mid is None or mid <= 0 or t <= 0:
        return None
    intrinsic = max(0.0, (s - k) if cp == 'c' else (k - s))
    if mid <= intrinsic:
        return 0.001
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
    if sigma is None or (isinstance(sigma, float) and math.isnan(sigma)) or sigma <= 0:
        return 1.0 if (cp == 'c' and s > k) else (0.0 if cp == 'c' else (-1.0 if s < k else 0.0))
    d1 = (math.log(s / k) + (RATE + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    if cp == 'c':
        return _N(d1)
    return _N(d1) - 1.0


def bs_gamma(s, k, t, sigma):
    """Gamma (Change in Delta per $1 Spot move)."""
    if sigma is None or (isinstance(sigma, float) and math.isnan(sigma)) or sigma <= 0 or t <= 0:
        return 0.0
    d1 = (math.log(s / k) + (RATE + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    return math.exp(-0.5 * d1 * d1) / (s * sigma * math.sqrt(2 * math.pi * t))


# ─── Datenquellen ──────────────────────────────────────────────────────────

def fetch_yahoo_data():
    """Holt SPY + VIX von Yahoo Finance."""
    spy = yf.Ticker(SPY_TICKER)
    vix = yf.Ticker(VIX_TICKER)

    # Historie für technische Levels
    hist_1y = spy.history(period="1y")
    hist_3m = spy.history(period="3mo")
    hist_5d = spy.history(period="5d")

    if hist_1y.empty:
        return None, "Yahoo 1y history leer"

    spot = float(hist_1y['Close'].iloc[-1])
    prev_close = float(hist_1y['Close'].iloc[-2]) if len(hist_1y) >= 2 else spot
    high_1y = float(hist_1y['High'].max())
    low_1y = float(hist_1y['Low'].min())
    high_52w = float(hist_1y['High'].tail(252).max())
    low_52w = float(hist_1y['Low'].tail(252).min())

    # SMAs
    sma_20 = float(hist_3m['Close'].rolling(20).mean().iloc[-1]) if len(hist_3m) >= 20 else None
    sma_50 = float(hist_3m['Close'].rolling(50).mean().iloc[-1]) if len(hist_3m) >= 50 else None
    sma_200 = float(hist_1y['Close'].rolling(200).mean().iloc[-1]) if len(hist_1y) >= 200 else None

    # VIX
    vix_hist = vix.history(period="5d")
    vix_spot = float(vix_hist['Close'].iloc[-1]) if not vix_hist.empty else None
    vix_prev = float(vix_hist['Close'].iloc[-2]) if not vix_hist.empty and len(vix_hist) >= 2 else None

    # Pivot Points (Klassisch: HLC Vortag)
    if len(hist_5d) >= 2:
        prev = hist_5d.iloc[-2]
        h, l, c = float(prev['High']), float(prev['Low']), float(prev['Close'])
    else:
        h, l, c = high_1y, low_1y, spot

    pp = (h + l + c) / 3.0
    r1 = 2 * pp - l
    r2 = pp + (h - l)
    r3 = r1 + (h - l)
    s1 = 2 * pp - h
    s2 = pp - (h - l)
    s3 = s1 - (h - l)

    # Volume (gestern)
    volume = int(hist_1y['Volume'].iloc[-1]) if not hist_1y.empty else None
    avg_volume = int(hist_1y['Volume'].tail(20).mean()) if len(hist_1y) >= 20 else None

    return {
        "spot": round(spot, 2),
        "prev_close": round(prev_close, 2),
        "change_pct": round((spot / prev_close - 1) * 100, 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "sma_20": round(sma_20, 2) if sma_20 else None,
        "sma_50": round(sma_50, 2) if sma_50 else None,
        "sma_200": round(sma_200, 2) if sma_200 else None,
        "pivot": {
            "pp": round(pp, 2),
            "r1": round(r1, 2),
            "r2": round(r2, 2),
            "r3": round(r3, 2),
            "s1": round(s1, 2),
            "s2": round(s2, 2),
            "s3": round(s3, 2),
        },
        "volume": volume,
        "avg_volume_20d": avg_volume,
        "vix": {
            "spot": round(vix_spot, 2) if vix_spot else None,
            "prev_close": round(vix_prev, 2) if vix_prev else None,
            "change_pct": round((vix_spot / vix_prev - 1) * 100, 2) if vix_spot and vix_prev else None,
        },
    }, None


def fetch_rix_chain():
    """SPY-Kette von RixTrade, in der Feldform der CBOE-Antwort.

    Damit bleiben die Auswertungen unveraendert: gleiche Schluessel
    (`option`, `bid`, `ask`, `delta`, `gamma`, `open_interest`, `volume`),
    gleiche Gruppierung nach YYMMDD.
    """
    import sys as _sys
    _sys.path.insert(0, "/opt/data/scripts")
    try:
        import rix_feed
        p = rix_feed.kette("SPY")
    except Exception as e:
        return None, f"RixTrade-Fehler: {e}"

    contracts = p.get("contracts") or []
    if not contracts:
        return None, "RixTrade: keine Kontrakte"

    by_expiry = {}
    ivs = []
    for c in contracts:
        try:
            yy = datetime.strptime(str(c["expiration"]), "%Y-%m-%d").strftime("%y%m%d")
            strike = float(c["strike"])
        except (KeyError, TypeError, ValueError):
            continue
        right = "C" if str(c.get("right", "")).upper().startswith("C") else "P"
        sym = "SPY%s%s%08d" % (yy, right, int(round(strike * 1000)))
        if c.get("iv"):
            ivs.append(float(c["iv"]))
        by_expiry.setdefault(yy, []).append({
            "option": sym,
            "bid": c.get("bid"),
            "ask": c.get("ask"),
            "delta": c.get("delta"),
            "gamma": c.get("gamma"),
            "open_interest": c.get("open_interest"),
            "volume": c.get("volume"),
            "iv": c.get("iv"),
        })

    iv30 = statistics.median(ivs) if ivs else None
    return {
        "cboe_spot": p.get("underlying_price"),
        "iv30": iv30,
        "expiries": sorted(by_expiry.keys()),
        "by_expiry": by_expiry,
    }, None


def fetch_cboe_chain():
    """RixTrade zuerst, CBOE nur als Rueckfall (15 Min Verzoegerung)."""
    rix, fehler = fetch_rix_chain()
    if rix is not None:
        return rix, None
    cboe, cboe_fehler = _fetch_cboe_chain_raw()
    if cboe is None:
        return None, fehler or cboe_fehler
    return cboe, None


def _fetch_cboe_chain_raw():
    """Holt SPY Options-Chain von CBOE (kostenlos, ~15min delayed)."""
    try:
        resp = requests.get(CBOE_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return None, f"CBOE-Fehler: {e}"

    options = data.get('data', {}).get('options', [])
    if not options:
        return None, "CBOE: Keine Optionen in der Response"

    cboe_spot = data['data'].get('current_price')
    iv30 = data['data'].get('iv30')

    # Nach Expiry sortieren
    by_expiry = {}
    for opt in options:
        sym = opt.get('option', '')
        expiry = sym[3:9]  # YYMMDD
        by_expiry.setdefault(expiry, []).append(opt)

    return {
        "cboe_spot": cboe_spot,
        "iv30": iv30,
        "expiries": list(sorted(by_expiry.keys())),
        "by_expiry": by_expiry,
    }, None


def parse_cboe_symbol(sym):
    """Parse CBOE-Symbol wie SPY260828C00560000 → (expiry, type, strike)."""
    # SPY{YYMMDD}{C|P}{STRIKE×1000, 8-stellig}
    expiry = sym[3:9]  # YYMMDD
    opt_type = sym[9]  # C oder P
    strike = int(sym[-8:]) / 1000.0
    return expiry, opt_type, strike


def hours_to_expiry(exp_ymd):
    """Stunden bis zum Verfall (16:00 ET)."""
    exp = datetime.strptime(exp_ymd, '%y%m%d').replace(
        hour=16, minute=0, tzinfo=ET
    )
    now = datetime.now(ET)
    return max((exp - now).total_seconds() / 3600.0, 0.0)


# ─── Berechnungen ──────────────────────────────────────────────────────────

def analyze_chain(chain_data, spot):
    """Berechne GEX, Walls, Expected Move, Max Pain aus CBOE-Chain."""
    if not chain_data:
        return None

    by_expiry = chain_data["by_expiry"]
    expiries = sorted(by_expiry.keys())

    # Nächstes Expiry finden (heute oder nächstes)
    now_et = datetime.now(ET)
    today_str = now_et.strftime('%y%m%d')

    target_exp = None
    for e in expiries:
        if e >= today_str:
            target_exp = e
            break
    if not target_exp:
        target_exp = expiries[0]

    opts = by_expiry[target_exp]
    t_hours = hours_to_expiry(target_exp)
    t_years = t_hours / 8760.0

    calls = []
    puts = []
    total_premium = 0
    sum_oi_straddle = 0  # für Expected Move

    for opt in opts:
        sym = opt.get('option', '')
        try:
            _, opt_type, strike = parse_cboe_symbol(sym)
        except (ValueError, IndexError):
            continue

        bid = opt.get('bid') or 0
        ask = opt.get('ask') or 0
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0
        oi = opt.get('open_interest') or 0
        vol = opt.get('volume') or 0
        iv = opt.get('iv') or 0
        if isinstance(iv, float) and math.isnan(iv):
            iv = 0

        # Greeks von CBOE (falls vorhanden) oder BS berechnen
        delta_cboe = opt.get('delta')
        gamma_cboe = opt.get('gamma')

        if delta_cboe is not None and not (isinstance(delta_cboe, float) and math.isnan(delta_cboe)):
            delta = delta_cboe
        else:
            delta = bs_delta(opt_type, spot, strike, t_years, iv / 100.0)

        if gamma_cboe is not None and not (isinstance(gamma_cboe, float) and math.isnan(gamma_cboe)):
            gamma = gamma_cboe
        else:
            sigma = iv / 100.0 if iv > 0 else None
            gamma = bs_gamma(spot, strike, t_years, sigma)

        # GEX = gamma * spot * 100 * OI
        gex = gamma * spot * 100 * oi
        if isinstance(gex, float) and math.isnan(gex):
            gex = 0.0
        dollar_premium = oi * mid * 100

        entry = {
            "strike": strike,
            "type": opt_type,
            "bid": round(bid, 2),
            "ask": round(ask, 2),
            "mid": round(mid, 2),
            "iv": round(iv, 1),
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "gex": round(gex, 0),
            "oi": int(oi),
            "volume": int(vol),
            "dollar_premium": round(dollar_premium, 0),
        }

        if opt_type == 'C':
            calls.append(entry)
        else:
            puts.append(entry)

        total_premium += dollar_premium

    # Sortieren nach Strike
    calls.sort(key=lambda x: x['strike'])
    puts.sort(key=lambda x: x['strike'])

    # GEX-Walls
    call_gex = {c['strike']: c['gex'] for c in calls if c['gex'] != 0}
    put_gex = {p['strike']: p['gex'] for p in puts if p['gex'] != 0}

    call_wall_gex = max(call_gex, key=call_gex.get) if call_gex else None
    put_wall_gex = max(put_gex, key=put_gex.get) if put_gex else None

    # OI-Walls
    call_oi = {c['strike']: c['oi'] for c in calls}
    put_oi = {p['strike']: p['oi'] for p in puts}

    call_wall_oi = max(call_oi, key=call_oi.get) if call_oi else None
    put_wall_oi = max(put_oi, key=put_oi.get) if put_oi else None

    # Max Pain = Strike mit minimalem totalen Payout (alle Optionen verfallen bei K)
    all_mp_strikes = sorted(set([c['strike'] for c in calls] + [p['strike'] for p in puts]))
    best_mp_strike = None
    best_mp_value = float('inf')
    for k in all_mp_strikes:
        pain = 0
        for c in calls:
            pain += c['oi'] * max(0, k - c['strike']) * 100
        for p in puts:
            pain += p['oi'] * max(0, p['strike'] - k) * 100
        if pain < best_mp_value:
            best_mp_value = pain
            best_mp_strike = k

    # Zero Gamma (Vorzeichenwechsel im Netto-GEX)
    all_strikes = sorted(set([c['strike'] for c in calls] + [p['strike'] for p in puts]))
    cum_gex = 0
    zero_gamma = None
    for s in all_strikes:
        c_gex = sum(c['gex'] for c in calls if c['strike'] == s)
        p_gex = sum(p['gex'] for p in puts if p['strike'] == s)
        net = c_gex + p_gex  # Calls +, Puts -
        prev_cum = cum_gex
        cum_gex += net
        if prev_cum >= 0 and cum_gex < 0:
            zero_gamma = s
            break
    if zero_gamma is None:
        zero_gamma = all_strikes[len(all_strikes) // 2] if all_strikes else spot

    # Expected Move (ATM Straddle)
    atm = min(all_strikes, key=lambda s: abs(s - spot)) if all_strikes else spot
    atm_call = next((c for c in calls if c['strike'] == atm), None)
    atm_put = next((p for p in puts if p['strike'] == atm), None)
    if atm_call and atm_put:
        expected_move = round(atm_call['mid'] + atm_put['mid'], 2)
        expected_move_pct = round(expected_move / spot * 100, 2)
    else:
        expected_move = None
        expected_move_pct = None

    # Netto GEX (alle Strikes)
    total_call_gex = round(sum(c['gex'] for c in calls), 0)
    total_put_gex = round(sum(p['gex'] for p in puts), 0)
    if math.isnan(total_call_gex):
        total_call_gex = 0.0
    if math.isnan(total_put_gex):
        total_put_gex = 0.0
    net_gex = round(total_call_gex + total_put_gex, 0)
    if math.isnan(net_gex):
        net_gex = 0.0

    # Bias aus GEX
    if net_gex > 0:
        gex_bias = "bullish"
    elif net_gex < -500000:
        gex_bias = "bearish"
    else:
        gex_bias = "neutral"

    return {
        "expiry": f"20{target_exp[:2]}-{target_exp[2:4]}-{target_exp[4:6]}",
        "dte": max(1, round(t_hours / 24)),
        "hours_to_expiry": round(t_hours, 1),
        "atm_strike": atm,
        "spot_vs_atm": round(spot - atm, 2),
        "expected_move": expected_move,
        "expected_move_pct": expected_move_pct,
        "max_pain": best_mp_strike,
        "zero_gamma": zero_gamma,
        "calls": {
            "total_oi": int(sum(c['oi'] for c in calls)),
            "total_volume": int(sum(c['volume'] for c in calls)),
            "total_gex": int(total_call_gex),
            "wall_gex": {"strike": call_wall_gex, "gex": int(call_gex.get(call_wall_gex, 0))} if call_wall_gex else None,
            "wall_oi": {"strike": call_wall_oi, "oi": int(call_oi.get(call_wall_oi, 0))} if call_wall_oi else None,
        },
        "puts": {
            "total_oi": int(sum(p['oi'] for p in puts)),
            "total_volume": int(sum(p['volume'] for p in puts)),
            "total_gex": int(total_put_gex),
            "wall_gex": {"strike": put_wall_gex, "gex": int(put_gex.get(put_wall_gex, 0))} if put_wall_gex else None,
            "wall_oi": {"strike": put_wall_oi, "oi": int(put_oi.get(put_wall_oi, 0))} if put_wall_oi else None,
        },
        "net_gex": int(net_gex),
        "gex_bias": gex_bias,
        "total_premium": int(total_premium),
        "atm_straddle": {
            "call_mid": round(atm_call['mid'], 2) if atm_call else None,
            "put_mid": round(atm_put['mid'], 2) if atm_put else None,
            "call_iv": round(atm_call['iv'], 1) if atm_call else None,
            "put_iv": round(atm_put['iv'], 1) if atm_put else None,
        },
        "top_oi_strikes": [
            {"strike": s['strike'], "type": s['type'], "oi": s['oi'], "dollar_premium": s['dollar_premium']}
            for s in sorted(calls + puts, key=lambda x: x['oi'], reverse=True)[:10]
        ],
    }, None


# ─── Hauptfunktion ─────────────────────────────────────────────────────────

def build_signal():
    """Sammelt alle Daten und gibt ein strukturiertes Signal-JSON zurück."""
    errors = []
    warnings = []

    # 1. Yahoo-Daten (Spot, VIX, Technische Levels)
    yahoo_data, err = fetch_yahoo_data()
    if err:
        errors.append(err)
        return {"error": errors[0], "partial": True}

    spot = yahoo_data["spot"]

    # 2. CBOE Options-Chain
    cboe_data, err = fetch_cboe_chain()
    if err:
        warnings.append(err)
        chain_analysis = None
    else:
        chain_analysis, err = analyze_chain(cboe_data, spot)
        if err:
            warnings.append(err)

    # 3. Marktregime bestimmen
    vix = yahoo_data.get("vix", {}).get("spot")
    if vix is not None:
        if vix > 25:
            vix_regime = "high_vol"
        elif vix > 16.5:
            vix_regime = "elevated"
        elif vix > 12:
            vix_regime = "normal"
        else:
            vix_regime = "low_vol"
    else:
        vix_regime = "unknown"

    # Trend-Regime
    sma20 = yahoo_data.get("sma_20")
    sma50 = yahoo_data.get("sma_50")
    sma200 = yahoo_data.get("sma_200")

    if sma20 and sma50:
        if spot > sma20 > sma50:
            trend = "bullish"
        elif spot < sma20 < sma50:
            trend = "bearish"
        elif abs(spot - sma20) / sma20 < 0.005:
            trend = "neutral"
        else:
            trend = "mixed"
    else:
        trend = "unknown"

    # No-Trade-Filter
    no_trade_reasons = []
    if vix is not None and vix > 16.5:
        no_trade_reasons.append(f"VIX={vix} > 16,5")
    if chain_analysis and chain_analysis["expected_move_pct"] and chain_analysis["expected_move_pct"] > 3:
        no_trade_reasons.append(f"Expected Move {chain_analysis['expected_move_pct']}% > 3%")

    # 4. Signal-JSON bauen
    signal = {
        "timestamp": datetime.now(BERLIN).isoformat(),
        "source": "rix_signal.py",
        "market_context": {
            "spx_proxy": {
                "spot": yahoo_data["spot"],
                "prev_close": yahoo_data["prev_close"],
                "change_pct": yahoo_data["change_pct"],
                "high_52w": yahoo_data["high_52w"],
                "low_52w": yahoo_data["low_52w"],
                "volume": yahoo_data["volume"],
                "avg_volume_20d": yahoo_data["avg_volume_20d"],
            },
            "vix": yahoo_data["vix"],
            "technical": {
                "sma_20": yahoo_data["sma_20"],
                "sma_50": yahoo_data["sma_50"],
                "sma_200": yahoo_data["sma_200"],
                "pivot": yahoo_data["pivot"],
                "trend": trend,
            },
            "vix_regime": vix_regime,
        },
        "options_chain": chain_analysis,
        "filters": {
            "vix_no_trade": vix is not None and vix > 16.5,
            "no_trade_reasons": no_trade_reasons,
            "can_trade": len(no_trade_reasons) == 0,
        },
        "warnings": warnings if warnings else None,
        "errors": errors if errors else None,
    }

    return signal


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    signal = build_signal()
    # Pretty-Print für Lesbarkeit, kompakt für Token-Effizienz
    print(json.dumps(signal, indent=2, default=str))
