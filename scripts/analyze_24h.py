import ccxt
import pandas as pd
import os
import sys
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.trade_persistence import TradePersistence

# Load env
load_dotenv()

def analyze_24h():
    print("Loading trades from local persistence...")
    try:
        persistence = TradePersistence()
        all_trades_raw = persistence.get_all_trades()
    except Exception as e:
        print(f"Error loading persistence: {e}")
        return

    # 1. Filter Trades (Last 24 Hours)
    now_ms = int(datetime.now().timestamp() * 1000)
    since = now_ms - (24 * 60 * 60 * 1000)
    
    all_trades = [t for t in all_trades_raw if t['timestamp'] >= since]
    
    if not all_trades:
        print("No trades found in the last 24 hours (from local persistence).")
        # Fallback: Try fetching if local is empty? 
        # For now, let's assume local is up to date since we just ran fetch_full_history.py
        return

    print(f"Found {len(all_trades)} trades in the last 24 hours.")

    # 2. Convert to DataFrame
    df = pd.DataFrame(all_trades)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 3. Analyze
    print("\n" + "="*50)
    print("24H TRADING ANALYSIS")
    print("="*50)
    
    # Filter for realized PnL (Close positions)
    # In Binance Futures, realizedPnl is in the 'info' dict
    def get_realized_pnl(row):
        return float(row['info'].get('realizedPnl', 0))

    def get_commission(row):
        return float(row['info'].get('commission', 0))
        
    def get_side(row):
        return row['side'] # 'buy' or 'sell'

    def get_position_side(row):
        # Infer position side: 
        # If realizedPnl != 0, it's a closing trade.
        # If side is SELL and PnL != 0, it was a LONG close.
        # If side is BUY and PnL != 0, it was a SHORT close.
        pnl = float(row['info'].get('realizedPnl', 0))
        side = row['side']
        if pnl != 0:
            if side == 'sell': return 'LONG'
            if side == 'buy': return 'SHORT'
        return 'OPEN'

    df['realized_pnl'] = df.apply(get_realized_pnl, axis=1)
    df['commission'] = df.apply(get_commission, axis=1)
    df['position_side'] = df.apply(get_position_side, axis=1)
    
    # Filter only closing trades (where PnL is realized)
    closed_trades = df[df['realized_pnl'] != 0].copy()
    
    total_trades = len(closed_trades)
    total_pnl = closed_trades['realized_pnl'].sum()
    total_fees = df['commission'].sum() # Fees apply to opens too
    net_pnl = total_pnl - total_fees
    
    winning_trades = closed_trades[closed_trades['realized_pnl'] > 0]
    losing_trades = closed_trades[closed_trades['realized_pnl'] <= 0]
    
    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
    
    print(f"Total Trades (Closed): {total_trades}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Total Realized PnL: ${total_pnl:.4f}")
    print(f"Total Fees: ${total_fees:.4f}")
    print(f"Net PnL: ${net_pnl:.4f}")
    
    print("\n--- Breakdown by Side ---")
    longs = closed_trades[closed_trades['position_side'] == 'LONG']
    shorts = closed_trades[closed_trades['position_side'] == 'SHORT']
    
    print(f"LONGs: {len(longs)} | PnL: ${longs['realized_pnl'].sum():.4f}")
    print(f"SHORTs: {len(shorts)} | PnL: ${shorts['realized_pnl'].sum():.4f}")
    
    print("\n--- Breakdown by Symbol ---")
    by_symbol = closed_trades.groupby('symbol')['realized_pnl'].sum().sort_values()
    print(by_symbol)

    print("\n--- Recent Losing Trades (Last 5) ---")
    if not losing_trades.empty:
        cols = ['datetime', 'symbol', 'position_side', 'price', 'amount', 'realized_pnl']
        print(losing_trades.sort_values('datetime', ascending=False).head(5)[cols])

    # Save to file for record
    os.makedirs('data/analysis', exist_ok=True)
    report_path = f'data/analysis/report_{datetime.now().strftime("%Y%m%d")}.txt'
    with open(report_path, 'w') as f:
        f.write(f"Analysis Time: {datetime.now()}\n")
        f.write(f"Win Rate: {win_rate:.2f}%\n")
        f.write(f"Net PnL: {net_pnl:.4f}\n")
    print(f"\nReport saved to {report_path}")

if __name__ == "__main__":
    analyze_24h()
