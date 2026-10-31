#!/usr/bin/env python3
"""Swing Trade Screener — Mega Caps + Momentum Stocks.

Scannt täglich nach Aktien an Unterstützung mit Catalyst-Potential.
Output: strukturiertes JSON für AI-Entscheidungen.

Usage:
    source .venv/bin/activate && python swing_screener.py
"""

import json
import math
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import rix_compat as yf  # RixTrade zuerst, yfinance nur als Rueckfall
import requests

BERLIN = ZoneInfo("Europe/Berlin")

# ─── Watchlists ────────────────────────────────────────────────────────────

MEGA_CAPS = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet", "AMZN": "Amazon",
    "META": "Meta", "NVDA": "NVIDIA", "TSLA": "Tesla", "BRK-B": "Berkshire",
    "JPM": "JPMorgan", "V": "Visa", "JNJ": "Johnson & Johnson", "WMT": "Walmart",
    "MA": "Mastercard", "PG": "Procter & Gamble", "UNH": "UnitedHealth",
    "HD": "Home Depot", "DIS": "Disney", "CRM": "Salesforce",
    "NFLX": "Netflix", "ADBE": "Adobe", "INTC": "Intel", "AMD": "AMD",
    "PYPL": "PayPal", "UBER": "Uber", "KO": "Coca-Cola", "PEP": "PepsiCo",
    "BA": "Boeing", "CAT": "Caterpillar", "XOM": "Exxon", "CVX": "Chevron",
    "COST": "Costco", "NKE": "Nike", "ABNB": "Airbnb",
 "PLTR": "Palantir", "MU": "Micron", "PANW": "Palo Alto Networks",
 }

MOMENTUM_WATCH = [
    "PLTR", "MU", "PANW", "SNOW", "CRWD", "DASH", "RDDT", "ARM",
    "APP", "MSTR", "COIN", "HOOD", "SOFI", "CLSK", "RIOT", "MARA",
]

# Kombinierte Watchlist
ALL_TICKERS = list(set(list(MEGA_CAPS.keys()) + MOMENTUM_WATCH))


# ─── Indikatoren ───────────────────────────────────────────────────────────

def compute_rsi(prices, period=14):
    """RSI(14) aus Schlusskursen."""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_sma(prices, period):
    """Simple Moving Average."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def compute_atr(highs, lows, closes, period=14):
    """Average True Range."""
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(1, len(highs)):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs[-period:]) / period


def compute_macd(prices):
    """MACD + Signal + Histogramm."""
    if len(prices) < 26:
        return None, None, None
    ema12 = compute_ema(prices, 12)
    ema26 = compute_ema(prices, 26)
    if ema12 is None or ema26 is None:
        return None, None, None
    macd = ema12 - ema26
    signal = compute_ema([macd] * min(len(prices) - 25, 9), 9) if len(prices) >= 34 else None
    hist = macd - signal if signal else None
    return macd, signal, hist


def compute_ema(prices, period):
    """Exponential Moving Average."""
    if len(prices) < period:
        return None
    multiplier = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


# ─── Stock-Analyse ─────────────────────────────────────────────────────────

def analyze_stock(ticker, name):
    """Analysiert eine Aktie auf Swing-Trade-Setup."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        hist_3m = stock.history(period="3mo")
        hist_1m = stock.history(period="1mo")

        if hist.empty or len(hist) < 20:
            return None

        closes = hist['Close'].tolist()
        highs = hist['High'].tolist()
        lows = hist['Low'].tolist()
        volumes = hist['Volume'].tolist()

        spot = float(closes[-1])
        prev_close = float(closes[-2]) if len(closes) >= 2 else spot
        high_52w = float(max(highs))
        low_52w = float(min(lows))

        # Abstand zum 52W-Hoch
        dist_from_high_pct = round((spot / high_52w - 1) * 100, 2)

        # RSI
        rsi = compute_rsi(closes)
        rsi_1d_ago = compute_rsi(closes[:-1]) if len(closes) > 15 else None

        # SMAs
        sma_20 = compute_sma(closes, 20)
        sma_50 = compute_sma(closes, 50)
        sma_200 = compute_sma(closes, 200)

        # Volume
        avg_vol_20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None
        last_vol = volumes[-1] if volumes else None
        vol_ratio = round(last_vol / avg_vol_20, 2) if avg_vol_20 and avg_vol_20 > 0 else None

        # MACD
        macd, signal, hist = compute_macd(closes)

        # ATR
        atr = compute_atr(highs, lows, closes)

        # Change %
        change_pct = round((spot / prev_close - 1) * 100, 2)

        # 5-Tage Performance
        perf_5d = round((spot / closes[-6] - 1) * 100, 2) if len(closes) >= 6 else None

        # ── Echte Support-Levels prüfen ──
        support_levels = []
        support_type = None
        support_price = None
        support_dist = None

        # SMA50 als Support (in Aufwärtstrend)
        if sma_50 and spot >= sma_50 * 0.97 and spot <= sma_50 * 1.03:
            support_levels.append(("SMA50", round(sma_50, 2)))
        # SMA200 als Support (stärker)
        if sma_200 and spot >= sma_200 * 0.97 and spot <= sma_200 * 1.03:
            support_levels.append(("SMA200", round(sma_200, 2)))
        # Vorheriges Swing Low aus 3-Monats-Daten
        if len(hist_3m) > 10:
            hl_3m = hist_3m['Low'].tolist()
            swing_lows_3m = sorted(set(hl_3m))[:5]  # 5 tiefste Punkte in 3 Monaten
            for sl in swing_lows_3m:
                if spot >= sl * 0.97 and spot <= sl * 1.03:
                    support_levels.append(("SwingLow", round(sl, 2)))
                    break
        # 52W Low
        if low_52w and spot >= low_52w * 0.97 and spot <= low_52w * 1.05:
            support_levels.append(("52W Low", round(low_52w, 2)))

        # Besten Support auswählen (nächsten zum Spot)
        if support_levels:
            best = min(support_levels, key=lambda x: abs(spot - x[1]))
            support_type = best[0]
            support_price = best[1]
            support_dist = round((spot / support_price - 1) * 100, 2)
        else:
            # Fallback: 20-Tage-Tief
            support_price = round(min(lows[-20:]), 2) if len(lows) >= 20 else None
            support_dist = round((spot / support_price - 1) * 100, 2) if support_price else None

        # Resistance (20-Tage-Hoch)
        resistance = round(max(highs[-20:]), 2) if len(highs) >= 20 else None

        # ── Swing Setup Score (strenge Kriterien) ──
        score = 0
        setup_signals = []
        risk_factors = []

        # Prüfung: Zu weit gefallen (> 40 % vom Hoch) = strukturelles Problem
        too_far_gone = dist_from_high_pct <= -40

        # Kriterium 1: Gefallen 5-30% vom Hoch (Sweet Spot für Swing)
        if -30 <= dist_from_high_pct <= -5:
            score += 1
            setup_signals.append(f"-{abs(dist_from_high_pct)}% vom Hoch")
        elif dist_from_high_pct < -30 and not too_far_gone:
            score += 0  # neutral, aber beobachten
            setup_signals.append(f"-{abs(dist_from_high_pct)}% (tief, Vorsicht)")
        elif too_far_gone:
            risk_factors.append(f"⚠ -{abs(dist_from_high_pct)}% vom Hoch (Wertvernichtung)")

        # Kriterium 2: RSI oversold + steigend (KLASSISCHER Swing-Signal)
        rsi_reversal = False
        if rsi is not None:
            if rsi < 30:
                score += 2
                setup_signals.append(f"RSI {rsi:.0f} (tief oversold)")
                if rsi_1d_ago is not None and rsi > rsi_1d_ago:
                    score += 2
                    rsi_reversal = True
                    setup_signals.append("RSI-Reversal ↑")
            elif rsi < 35:
                score += 1
                setup_signals.append(f"RSI {rsi:.0f} (oversold)")
                if rsi_1d_ago is not None and rsi > rsi_1d_ago:
                    score += 1
                    rsi_reversal = True
                    setup_signals.append("RSI steigt ↑")
            elif rsi < 40 and rsi_1d_ago is not None and rsi > rsi_1d_ago and rsi_1d_ago < 35:
                # Kam aus Oversold, steigt weiter
                score += 1
                setup_signals.append("RSI erholt sich ↑")

        # Kriterium 3: Über SMA 200 (strukturell intakt) — essentiell
        if sma_200 and spot > sma_200:
            score += 2
            setup_signals.append(f"Über SMA200 ({sma_200:.0f})")
        elif sma_200 and spot < sma_200:
            risk_factors.append(f"Unter SMA200 ({sma_200:.0f})")
            # Wenn nur knapp drunter und RSI-Reversal: trotzdem 1 Punkt
            if sma_200 and (sma_200 * 0.95) < spot < sma_200 and rsi_reversal:
                score += 1
                setup_signals.append(f"Knapp unter SMA200, RSI-Reversal")

        # Kriterium 4: Volumen-Bestätigung (wichtig)
        if vol_ratio and vol_ratio > 2.0:
            score += 2
            setup_signals.append(f"Volumen {vol_ratio}× 🚀")
        elif vol_ratio and vol_ratio > 1.5:
            score += 1
            setup_signals.append(f"Volumen {vol_ratio}×")

        # Kriterium 5: MACD-Konvergenz (Histogramm wird positiver)
        if hist is not None and signal is not None and macd is not None:
            if macd > signal:
                score += 1
                setup_signals.append("MACD bullish")

        # Kriterium 6: RSI-Obergrenze — zu heiß = kein Einstieg
        if rsi is not None and rsi > 60:
            risk_factors.append(f"RSI {rsi:.0f} (zu heiß, Pullback abwarten)")
            if rsi > 70:
                score -= 3  # Stark überhitzt
            elif rsi > 65:
                score -= 2
            else:
                score -= 1

        # Kriterium 7: Momentum-Kategorie — Breakout-Retest / Pullback
        if ticker in MOMENTUM_WATCH:
            if perf_5d is not None and -2 <= perf_5d <= 2 and rsi < 45:
                # Pullback in Momentum-Stock = Einstiegschance
                score += 2
                setup_signals.append(f"Momentum-Pullback ({perf_5d:+.1f}% 5d)")
            elif perf_5d is not None and perf_5d > 5 and rsi > 50:
                # Breakout-Lauf — zu heiß für Einstieg
                risk_factors.append(f"Momentum überhitzt ({perf_5d:+.1f}% 5d, RSI {rsi:.0f})")

        # Kriterium 7: Support-Nähe (echte Levels)
        if support_type and support_price and support_dist is not None and support_dist <= 3:
            score += 1
            setup_signals.append(f"@{support_type} ({support_price})")
        elif support_price and spot / support_price - 1 < 0.05:
            score += 1  # nah am 20-Tage-Tief

        # Bias (verschärfte Schwellen)
        if score >= 7:
            bias = "strong_buy"
        elif score >= 4:
            bias = "buy"
        elif score <= 1 or too_far_gone:
            bias = "avoid"
        else:
            bias = "neutral"

        # Wenn zu viele Risikofaktoren: herabstufen
        if len(risk_factors) >= 2 and bias in ("strong_buy", "buy"):
            bias = "neutral"

        # Earnings-Datum (nächstes)
        earnings_date = None
        try:
            cal = stock.calendar
            if cal is not None and not cal.empty:
                if 'Earnings Date' in cal.index:
                    ed = cal.loc['Earnings Date']
                    if hasattr(ed, 'iloc'):
                        earnings_date = str(ed.iloc[0].date()) if hasattr(ed.iloc[0], 'date') else str(ed.iloc[0])
        except Exception:
            pass

        return {
            "ticker": ticker,
            "name": name,
            "spot": round(spot, 2),
            "change_pct": change_pct,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "dist_from_high_pct": dist_from_high_pct,
            "rsi_14": round(rsi, 1) if rsi else None,
            "sma_20": round(sma_20, 2) if sma_20 else None,
            "sma_50": round(sma_50, 2) if sma_50 else None,
            "sma_200": round(sma_200, 2) if sma_200 else None,
            "above_sma200": spot > sma_200 if sma_200 else None,
            "macd_bullish": bool(macd and signal and macd > signal) if macd and signal else None,
            "volume_ratio": vol_ratio,
            "atr": round(atr, 2) if atr else None,
            "perf_5d": perf_5d,
            "swing_score": score,
            "bias": bias,
            "support_type": support_type,
            "support_price": support_price,
            "support_dist_pct": support_dist,
            "resistance": resistance,
            "earnings_date": earnings_date,
            "setup_signals": setup_signals,
            "risk_factors": risk_factors,
            "category": "mega_cap" if ticker in MEGA_CAPS else "momentum",
        }
    except Exception as e:
        return None


# ─── Hauptfunktion ─────────────────────────────────────────────────────────

def run_screener():
    """Führt den vollständigen Screener aus."""
    results = []

    for ticker, name in sorted(MEGA_CAPS.items()):
        result = analyze_stock(ticker, name)
        if result:
            results.append(result)

    # Momentum-Stocks, die nicht schon in Mega Caps sind
    for ticker in MOMENTUM_WATCH:
        if ticker not in MEGA_CAPS:
            result = analyze_stock(ticker, ticker)
            if result:
                results.append(result)

    # Sortieren nach Swing Score (absteigend)
    results.sort(key=lambda x: x["swing_score"], reverse=True)

    # Aufbereiten
    setups = []
    for r in results:
        if r["bias"] in ("strong_buy", "buy"):
            setups.append({
                "ticker": r["ticker"],
                "name": r["name"],
                "spot": r["spot"],
                "bias": r["bias"],
                "score": r["swing_score"],
                "dist_from_high": r["dist_from_high_pct"],
                "rsi": r["rsi_14"],
                "above_sma200": r["above_sma200"],
                "volume_ratio": r["volume_ratio"],
                "support_type": r["support_type"],
                "support_price": r["support_price"],
                "support_dist_pct": r["support_dist_pct"],
                "resistance": r["resistance"],
                "signals": r["setup_signals"],
                "risk_factors": r["risk_factors"],
                "earnings": r["earnings_date"],
                "perf_5d": r["perf_5d"],
                "category": r["category"],
            })

    # Zusammenfassung
    total_scanned = len(results)
    buy_signals = len([r for r in results if r["bias"] in ("strong_buy", "buy")])
    strong_buys = len([r for r in results if r["bias"] == "strong_buy"])

    output = {
        "timestamp": datetime.now(BERLIN).isoformat(),
        "source": "swing_screener",
        "summary": {
            "total_scanned": total_scanned,
            "buy_signals": buy_signals,
            "strong_buys": strong_buys,
            "no_trade": len([r for r in results if r["bias"] == "avoid"]),
        },
        "top_setups": setups[:15],  # Top 15
        "market_context": {
            "spy_spot": None,
            "vix": None,
        },
    }

    # SPY + VIX Kontext
    try:
        spy = yf.Ticker("SPY")
        spy_h = spy.history(period="5d")
        if not spy_h.empty:
            output["market_context"]["spy_spot"] = round(float(spy_h['Close'].iloc[-1]), 2)

        vix = yf.Ticker("^VIX")
        vix_h = vix.history(period="5d")
        if not vix_h.empty:
            output["market_context"]["vix"] = round(float(vix_h['Close'].iloc[-1]), 2)
    except Exception:
        pass

    return output


if __name__ == "__main__":
    signal = run_screener()
    print(json.dumps(signal, indent=2, default=str))
