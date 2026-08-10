# Projekt: rix trading

**Erstellt:** 29. Juli 2026
**Account:** OptionsFunding Growth 100K (Evaluation)
**Plattform:** optionsfunding.co — RixTrade Dashboard
**Benutzer:** luckeeez
**Ziel:** $12.000 Profit (12%) → Funded Phase bestehen

## Aktueller Fokus
- **FOMC-Tag (29.07.)** — 14:00 ET / 20:00 MEZ Entscheidung
- **Trade-Plan:** 0DTE SPY Iron Condor (pre-FOMC) für IV-Crush
- **Alternativ:** Post-FOMC-Directional nach Entscheidung

## Parameter
- Trailing DD: $6.000 (End of Day)
- Consistency: 30%-Cap (bester Tag ≤ 30% aller Gewinntage)
- Alle Strategien erlaubt (Growth Plan)
- SPY bevorzugtes Instrument

## Referenzen
- `/opt/rix-trading/EVALUATION_STRATEGY.md` — Hauptstrategie
- `/opt/rix-trading/FOMC_20260729.md` — Heutiger FOMC-Trade
- `/opt/rix-trading/get_options_data.py` — Options-Daten-Fetcher
- `/opt/rix-trading/TRADE_LOG.yaml` — Trade-Log (Daten)
- `/opt/rix-trading/trade_log.py` — Log-Tooling: `status` / `add` / `check` (trackt Target, DD, Consistency automatisch)

## Tages-Rhythmus
- **Cron `📊 Rix Pre-Market Setup`** (`3a576333f62a`): Mo–Fr 15:30 Berlin (= 9:30 ET, US-Open) → Setup-Scan nach EVALUATION_STRATEGY.md, Zustellung in den Chat.
- Cron-Expressions laufen in **Berliner Zeit** (hermes_time), NICHT UTC — `30 15 * * 1-5` = 15:30 Berlin.
- **DST-Hinweis:** Berlin↔NY meist 6h Differenz; in der Übergangswoche (EU letzter So Okt vs. US erster So Nov) nur 5h → Scan kommt 1h „spät" (10:30 ET). Für Pre-Market-Scan unkritisch, aber im Hinterkopf behalten.
- **Trade-Log-Update:** nach Börsenschluss (21:55 ET / ~03:55 MEZ) Trades per `trade_log.py add` eintragen, `status` prüfen, committen + via `/opt/rix-trading` pushen (dort liegt der GitHub-Token in der Remote-URL).
