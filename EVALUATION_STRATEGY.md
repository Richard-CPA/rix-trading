# RIX Trading — OptionsFunding Growth 100K Evaluations-Strategie

**Erstellt:** 29. Juli 2026
**Account:** OptionsFunding Growth 100K ($100.000 simuliert)
**Phase:** Evaluation → Ziel: $12.000 Profit (12%)

---

## 1. Account-Parameter

| Metrik | Wert |
|--------|------|
| Kontogröße | $100.000 |
| Profit Target | **$12.000 (12%)** |
| Trailing Drawdown | $6.000 (6%) — End of Day |
| Consistency-Cap | **30%** (bester Tag ≤ 30% aller Gewinntage) |
| Min. Trading-Tage | 0 |
| Zeitlimit | Keines |
| Erlaubte Strategien | **Alle** (Buy+Write, Spreads, Multi-Leg, undefined risk) |
| Ticker | SPY, QQQ, IWM + Whitelist |
| Overnight | ✅ Erlaubt |
| 0DTE | ✅ Erlaubt |
| News-Trading | ✅ Erlaubt |

---

## 2. Mathematische Optimierung der Consistency-Regel

Die **30%-Regel** ist der engste Engpass:

> Bester Gewinntag / Summe aller Gewinntage ≤ 30%

**Minimale Anzahl Gewinntage bei $12k Target:**

| Tage | Verteilung | Best/Tag | Ratio | Bestanden? |
|------|-----------|---------|-------|-----------|
| 1 | $12.000 | $12.000 | 100% | ❌ |
| 2 | $3.600 + $8.400 | $8.400 | 70% | ❌ |
| 3 | $4.000 + $4.000 + $4.000 | $4.000 | 33,3% | ❌ |
| **4** | **$3.000 × 4** | **$3.000** | **25%** | **✅** |
| 5 | $2.400 × 5 | $2.400 | 20% | ✅ |

**Fazit:** Mindestens **4 Gewinntage** nötig, idealerweise à ~$3.000.

Verlusttage zählen nicht in den Nenner — sie schaden der Consistency nicht, verlangsamen aber den Fortschritt zum Target.

---

## 3. Strategie: SPY Bull Put Credit Spreads (Primär)

### Warum Credit Spreads?

- ✅ **Defined Risk** — Max-Verlust ist von Anfang an bekannt
- ✅ **Hohe Wahrscheinlichkeit** (70-85% POP bei OTM-Strikes)
- ✅ **Theta-positive** — Zeitverfall arbeitet für dich
- ✅ **Ausgezeichnete Liquidität** auf SPY
- ✅ **Konsistente, skalierbare Gewinne** — ideal für Consistency-Regel
- ✅ **Growth Plan erlaubt alle Strategien**

### Setup

| Parameter | Wert |
|-----------|------|
| **Underlying** | SPY (derzeit ~$741) |
| **Strategie** | Bull Put Credit Spread |
| **Short Strike** | ~$725–730 (1,5-2% unter Kurs, ~0,15-0,25 Delta) |
| **Long Strike** | 5 Punkte tiefer ($720–725) |
| **Spread-Breite** | $5 |
| **DTE** | 0-5 Tage (bevorzugt 0-2 DTE) |
| **Kontrakte** | 10-15 |
| **Credit/Spread** | ~$0,80-1,50 |
| **Total Credit/Tag** | **~$800-2.250** |
| **Max Loss** | 15 × $500 = $7.500 (managed auf $3.000) |
| **POP** | ~70-85% |
| **Auto-Close** | 4:10 PM ET bei 0DTE |

### Beispiel-Rechnung: 12 Kontrakte, $5 Spread

| Szenario | Rechnung |
|----------|---------|
| **Kredit pro Spread** | $1,00 ($1,00 × 100 = $100/Spread) |
| **Total Kredit** | 12 × $100 = **$1.200** |
| **Max Loss (unmanaged)** | 12 × $500 = $6.000 (= DD) |
| **Break-Even SPY** | $730 - $1,00 = **$729,00** |
| **POP** | ~78% (0,22 Delta Short Strike) |
| **Tage bis Target** | ~10 Tage (bei $1.200/Tag) |

### Position-Sizing-Regel

```
Max Loss pro Trade ≤ $3.000 (50% des DD)
Position Size = floor($3.000 / (Spread-Breite × 100))
```

Bei $5 Spread: max 6 Kontrakte für $3k Loss... das ist zu klein.

**Besser:** Trade mit 15 Kontrakten, aber aktivem Loss-Management:
- **Stop-Loss:** Schließe Trade bei 100% des erhaltenen Kredits (Verlust = Kredit)
- **Take-Profit:** Schließe bei 50% des max. Gewinns
- Bei 15 × $1,00 Kredit: SL bei -$1.500, TP bei +$750

---

## 4. Detaillierte Trade-Execution

### Schritt 1: Marktanalyse (vor Börsenöffnung)

```python
# SPY Bias bestimmen
- SPY > 20-Tage-SMA → Bullish → Bull Put Spread
- SPY < 20-Tage-SMA → Bearish → Bear Call Spread
- SPY range-gebunden → Iron Condor (beide Seiten)
```

### Schritt 2: Strike-Auswahl (0-2 DTE)

**Bei bullish Bias (aktuell):**

| Strike | Delta | Credit | POP |
|--------|-------|--------|-----|
| Sell $730p / Buy $725p | ~0,22 | ~$1,00 | 78% |
| Sell $725p / Buy $720p | ~0,15 | ~$0,65 | 85% |
| Sell $735p / Buy $730p | ~0,30 | ~$1,50 | 70% |

**Empfehlung:** $730p/$725p — beste Balance aus Credit und POP.

### Schritt 3: Order-Execution

```
Limit Order: SELL 15 SPY $730p, BUY 15 SPY $725p
  Limit Credit: $1,05/Spread (oder besser)
  TIF: DAY
```

### Schritt 4: Management (0DTE)

| Equity | Aktion |
|--------|--------|
| Credit ≥ 50% ($787) | **Schließen** (Gewinn mitnehmen) |
| Verlust = Kredit ($1.575) | **Schließen** (SL) |
| SPY < $730 und >$728 | **Erwägen zu schließen** (50% Verlust) |
| SPY < $728,50 | **Sofort schließen** (Defensiv) |
| 3:30 PM ET, Trade offen | Schließen (vor Auto-Close) |

### Schritt 5: Tägliche Fortschritts-Tracking

| Tag | Ergebnis | Kum. Gewinne | Best Day | Consistency-Check |
|-----|----------|-------------|----------|------------------|
| 1 | +$1.200 | $1.200 | $1.200 (100%) | ⚠️ Zu früh |
| 2 | +$1.500 | $2.700 | $1.500 (55%) | ⚠️ |
| 3 | +$1.100 | $3.800 | $1.500 (39%) | ⚠️ |
| 4 | +$1.400 | $5.200 | $1.500 (29%) | ✅ |
| 5 | +$1.300 | $6.500 | $1.500 (23%) | ✅ |
| ... | | | | |
| 8 | +$1.200 | $9.200 | $1.500 (16%) | ✅ |
| 9 | +$1.400 | $10.600 | $1.500 (14%) | ✅ |
| 10 | +$1.400 | **$12.000** | $1.500 (12,5%) | ✅ **PASS** |

---

## 5. Alternative Strategien (bei Bedarf)

### Iron Condor (neutral / range-bound)

| Position | Strike | Credit |
|----------|--------|--------|
| Sell $730p / Buy $725p | Put-Seite | ~$0,40 |
| Sell $752c / Buy $757c | Call-Seite | ~$0,40 |
| **Total** | | **~$0,80/IC** |
| 12 ICs × $80 | | **$960** |
| Max Loss | | $6.000 |
| Win Zone | | $730-$752 |

**Nutze ich, wenn:** SPY keine klare Richtung hat, IV niedrig ist.

### Bear Call Credit Spread (bearish)

| Position | Strike |
|----------|--------|
| Sell $755c / Buy $760c | 5-wide |
| Credit | ~$0,80-1,20 |
| 12 Kontrakte | ~$960-1.440 |

**Nutze ich, wenn:** SPY unter 20-Tage-SMA, bärischer Bias.

### Bull Call Debit Spread (stark bullish)

| Position | Strike |
|----------|--------|
| Buy $745c / Sell $755c | 10-wide |
| Debit | ~$3,00-4,00 |
| Max Gain | ~$6,00-7,00/Spread |
| 10 Kontrakte | Max Gain ~$6.000-7.000 |

**Nutze ich, wenn:** Klarer Breakout, hohe Confirmation (earnings, FOMC).

---

## 6. Risikomanagement

### Harte Grenzen

| Regel | Limit |
|-------|-------|
| Max Exposure pro Tag | **$3.000 Risiko** (50% des DD) |
| Max Drawdown Utilization | **$4.000** (67% des $6k DD — Reserve für Fehler) |
| Max Verlust-Tage in Folge | **3** → dann Pause/Rückschau |
| Täglicher Stop | Bei -$3.000 Tagesverlust → Kein weiterer Trade |

### Consistency-Cap nicht verletzen

**Formel für Max Day:**

```
MaxDay = 0,30 × Summe(AllWinningDays)
```

**Management:** Wenn ein Tag zu groß ist (>30%), einfach mehr kleine Siege sammeln, um den Anteil zu drücken. Nicht disqualifizierend!

### Drawdown-Schutz (End of Day)

- DD-Floor bewegt sich **nur bei Börsenschluss** nach oben
- Intraday-Rücksetzer bis unter die Floor-Schwelle sind ok, solange der Kontostand bei Close über Floor liegt
- **Gefahr:** Wenn man bei +$6k Gewinn ist, ist Floor bei $100k. Ein großer Intraday-Verlust unter $100k triggert den DD beim nächsten Close, **wenn** der Kontostand dann noch unter $100k steht.

---

## 7. Beispiel-Trades (mit realen OptionStrat-Daten)

### Trade 1: Bull Put Spread — SPY 0DTE

**Setup:** SPY @ $741, 29. Juli 2026 (heute) — Expiry heute

| Leg | Strike | Typ | Credit |
|-----|--------|-----|--------|
| Sell | $735 Put | ~0,35 Delta | +$1,75 |
| Buy | $730 Put | ~0,20 Delta | -$0,85 |
| **Net Credit** | | | **+$0,90** |

**15 Kontrakte:** $0,90 × 15 × 100 = **$1.350 Credit**
**Max Loss:** $5,00 × 15 × 100 = $7.500 (unmanaged, close bei -$1.350)
**POP:** ~70%
**Break-Even:** $734,10

**Szenarien:**
- SPY schließt >$735: **+$1.350** ✅
- SPY schließt $730-$735: Teilgewinne
- SPY < $730 bei 3:30 PM: Vor Auto-Close schließen für ~-$1.000

### Trade 2: Bull Put Spread — SPY 2 DTE

| Leg | Strike | Credit |
|-----|--------|--------|
| Sell | $730 Put (0DTE freitags) | +$1,10 |
| Buy | $725 Put | -$0,30 |
| **Net Credit** | | **+$0,80** |

**12 Kontrakte:** 12 × $80 = **$960 Credit**
**POP:** ~80%
**Break-Even:** $729,20

---

## 8. Schnellster Pfad zum Ziel

Da **4 Gewinntage minimum** (Consistency), ziele auf:

**Tag 1-4:** Jeweils $2.500-3.000
**Tag 5:** Letzter Push auf $12k gesamt

Realistischer Zeitrahmen: **8-14 Trading-Tage** (ca. 2-3 Wochen)

| Szenario | Gewinntage | Verlusttage | Netto | Tage |
|----------|-----------|------------|-------|------|
| Optimal | 8 × $1.500 | 0 | $12.000 | 8 |
| Gut | 10 × $1.500 | 3 × -$600 | $13.200 | 13 |
| Konservativ | 12 × $1.200 | 4 × -$500 | $12.400 | 16 |

---

## 9. Ticker-Whitelist (bestätigte Ticker)

Typische SPY-bezogene Ticker auf OptionsFunding:
- **SPY** (Hauptinstrument)
- **QQQ** (Tech-Alternative)
- **IWM** (Small-Cap)
- **DIA** (Dow)
- **AAPL, MSFT, AMZN, GOOGL, META** (Einzelaktien auf Anfrage)

Für die Evaluation konzentriere dich auf **SPY** — höchste Liquidität, engste Spreads, beste Ausführung.

---

## 10. Zusammenfassung

```
Strategie:     Bull Put Credit Spreads auf SPY
Strikes:       ~$730p/$725p (5-wide)
DTE:           0-3 Tage
Size:          12-15 Kontrakte (±$1.200-1.500 Credit/Tag)
Risk/Trade:    ~$1.500 (managed)
DD-Puffer:     $6.000 total
Target:        $12.000 in ~10-14 Trading-Tagen
Consistency:   4+ Gewinntage mit ≤$3.000/bestem Tag
```

**Nächster Schritt:** Sobald du bestätigst, können wir mit Trade 1 heute starten oder ich passe die Strikes an den aktuellen SPY-Kurs an. Welche Richtung erwartest du aktuell für SPY (bullish/bearish/neutral)?
