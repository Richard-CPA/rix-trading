"""Drop-in-Ersatz fuer die verwendeten yfinance-Aufrufe, gespeist aus RixTrade.

Die Skripte nutzen ausschliesslich `yf.Ticker(sym).history(period=...)`.
Diese Datei bietet dieselbe Oberflaeche und liefert Kerzen von RixTrade
(`/api/bars/underlying/{symbol}`), mit automatischem Rueckfall auf yfinance,
falls die Sitzung tot ist oder ein Symbol fehlt.

Verwendung in einem Skript:  import rix_compat as yf
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, "/opt/data/scripts")
import rix_feed  # noqa: E402

_PERIODEN = {"1d": 3, "5d": 8, "1mo": 35, "3mo": 100, "6mo": 190, "1y": 370, "2y": 740, "5y": 1830}


def _symbol(sym: str) -> str:
    s = (sym or "").upper().strip()
    return {"^VIX": "VIX", "^SPX": "SPX", "I:SPX": "SPX", "^NDX": "NDX"}.get(s, s)


class Ticker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    def history(self, period: str = "1y", interval: str = "1d", **_):
        tage = _PERIODEN.get(period, 370)
        frm = (datetime.now(timezone.utc) - timedelta(days=tage)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            d = rix_feed.hole(
                f"/api/bars/underlying/{_symbol(self.symbol)}",
                {"interval": "1d", "from": frm},
            )
            bars = d.get("bars") or []
            if bars:
                df = pd.DataFrame(
                    {
                        "Open": [b.get("o") for b in bars],
                        "High": [b.get("h") for b in bars],
                        "Low": [b.get("l") for b in bars],
                        "Close": [b.get("c") for b in bars],
                        "Volume": [b.get("v") or 0 for b in bars],
                    },
                    index=pd.to_datetime([b["ts"] for b in bars], utc=True),
                ).dropna()
                df.index.name = "Date"
                return df
        except Exception:
            pass
        import yfinance as _yf

        return _yf.Ticker(self.symbol).history(period=period, interval=interval)
