"""Fetch SPY options chain for FOMC day trade planning."""
import yfinance as yf
import pandas as pd

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)
pd.set_option('display.float_format', '{:.2f}'.format)

spy = yf.Ticker('SPY')

# Get current price from recent data
hist = spy.history(period='2d')
print(f"SPY current: ~${hist['Close'].iloc[-1]:.2f}" if not hist.empty else "SPY: N/A")

# Get options expirations
expirations = spy.options
print(f"\nAvailable expirations ({len(expirations)} total):")
for e in expirations[:8]:
    print(f"  {e}")

# Nearest expiration
today_exp = expirations[0]
print(f"\n{'='*80}")
print(f"CHAIN FOR: {today_exp} (0DTE)")
print('='*80)

opt = spy.option_chain(today_exp)
calls = opt.calls
puts = opt.puts

# Filter near current price
strike_min, strike_max = 710, 770

print(f"\n--- CALLS ---")
cols = ['strike', 'bid', 'ask', 'lastPrice', 'impliedVolatility', 'delta', 'gamma', 'theta', 'vega', 'volume', 'openInterest']
calls_f = calls[(calls['strike'] >= strike_min) & (calls['strike'] <= strike_max)].copy()
for _, r in calls_f.iterrows():
    iv = r.get('impliedVolatility', 0)
    print(f"  {r['strike']:6.1f} | bid={r['bid']:5.2f} ask={r['ask']:5.2f} mid={((r['bid']+r['ask'])/2):5.2f} IV={iv:.1%} delta={r.get('delta',0):.2f} theta={r.get('theta',0):.2f} vega={r.get('vega',0):.2f} vol={r['volume']:5.0f} OI={r['openInterest']:6.0f}")

print(f"\n--- PUTS ---")
puts_f = puts[(puts['strike'] >= strike_min) & (puts['strike'] <= strike_max)].copy()
for _, r in puts_f.iterrows():
    iv = r.get('impliedVolatility', 0)
    print(f"  {r['strike']:6.1f} | bid={r['bid']:5.2f} ask={r['ask']:5.2f} mid={((r['bid']+r['ask'])/2):5.2f} IV={iv:.1%} delta={r.get('delta',0):.2f} theta={r.get('theta',0):.2f} vega={r.get('vega',0):.2f} vol={r['volume']:5.0f} OI={r['openInterest']:6.0f}")

# Compare IV with next expiration to see FOMC IV premium
if len(expirations) >= 2:
    next_exp = expirations[1]
    print(f"\n{'='*80}")
    print(f"CHAIN FOR: {next_exp} (next expiry)")
    print('='*80)
    opt2 = spy.option_chain(next_exp)
    # Just show ATM-ish strikes
    for exp_label, opt_chain in [(today_exp, opt), (next_exp, opt2)]:
        calls2 = opt_chain.calls
        puts2 = opt_chain.puts
        atm_strike = 740
        print(f"\nATM ({atm_strike}) comparison:")
        c = calls2[calls2['strike'] == atm_strike]
        p = puts2[puts2['strike'] == atm_strike]
        if not c.empty:
            r = c.iloc[0]
            print(f"  Call {exp_label}: mid={((r['bid']+r['ask'])/2):.2f} IV={r.get('impliedVolatility',0):.1%}")
        if not p.empty:
            r = p.iloc[0]
            print(f"  Put  {exp_label}: mid={((r['bid']+r['ask'])/2):.2f} IV={r.get('impliedVolatility',0):.1%}")
