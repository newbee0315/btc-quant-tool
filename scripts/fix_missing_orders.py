
import sys
import os
import json
import logging
import traceback
from pprint import pprint

import time

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.trader.real_trader import RealTrader

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '../trader_config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return None

def main():
    print("=== Fixing Missing SL/TP Orders ===")
    
    config = load_config()
    if not config:
        print("❌ Error: trader_config.json not found!")
        return

    # Load params
    sl_pct = config.get('sl_pct', 0.04)
    tp_pct = config.get('tp_pct', 0.06)
    
    print(f"Loaded Config: Mode={config.get('mode')}, SL={sl_pct:.1%}, TP={tp_pct:.1%}")
    
    # Initialize Trader
    try:
        trader = RealTrader(
            symbol="BTC/USDT:USDT", # Init with default, but we will handle all symbols
            leverage=20,
            api_key=config.get('api_key'),
            api_secret=config.get('api_secret'),
            proxy_url=config.get('proxy_url')
        )
        
        if not trader.exchange:
            print("❌ Trader initialized but exchange is None.")
            return

        # Suppress warning for global fetch
        trader.exchange.options['warnOnFetchOpenOrdersWithoutSymbol'] = False
        
        # Force load markets
        trader.exchange.load_markets()
            
        print("✅ Exchange initialized successfully!")
        
        # Fetch Positions
        positions = trader.get_positions()
        if not positions:
            print("No open positions found.")
            return

        # DEBUG: Fetch ALL open orders to see if they exist under different symbols
        print("   [DEBUG] Fetching ALL open orders (no symbol filter)...")
        try:
            all_open = trader.exchange.fetch_open_orders()
            print(f"   [DEBUG] Found {len(all_open)} total open orders.")
            for o in all_open:
                 print(f"     > Sym: {o['symbol']} | ID: {o['id']} | Type: {o['type']} | Status: {o['status']}")
        except Exception as e:
            print(f"   [DEBUG] Failed to fetch all open orders: {e}")

        for sym, pos in positions.items():
            print(f"\nProcessing {sym} ({pos['side']})...")
            
            # Test Mode: Only process SOL
            if "SOL" not in sym:
                 continue

            # DEBUG: Place a plain LIMIT order (Far away)
            print("   [DEBUG] Placing a dummy LIMIT order (Buy SOL at $10)...")
            try:
                # Use strict symbol resolution for dummy order
                dummy_sym = sym
                
                # 0.2 SOL * $10 = $2 (Too small). Need > $5.
                # Use 0.6 SOL * $10 = $6.
                dummy_order = trader.exchange.create_order(dummy_sym, 'LIMIT', 'buy', 0.6, price=10.0)
                print(f"   [DEBUG] Dummy Order Response: {json.dumps(dummy_order, default=str)}")
                print("   [DEBUG] Checking if dummy order exists in open orders...")
                time.sleep(2)
                
                # Check specific symbol
                open_orders = trader.exchange.fetch_open_orders(dummy_sym)
                found_dummy = False
                for o in open_orders:
                    print(f"     [DEBUG Check] ID: {o['id']}, Type: {o['type']}, Status: {o['status']}")
                    if str(o['id']) == str(dummy_order['id']):
                        found_dummy = True
                        print("   [DEBUG] ✅ Dummy Order FOUND in Open Orders!")
                        # Cancel it
                        trader.exchange.cancel_order(o['id'], dummy_sym)
                        print("   [DEBUG] Dummy Order Cancelled.")
                
                if not found_dummy:
                    print("   [DEBUG] ❌ Dummy Order NOT FOUND in Open Orders!")
                    # Check ALL again
                    try:
                        all_open_again = trader.exchange.fetch_open_orders()
                        for o in all_open_again:
                             if str(o['id']) == str(dummy_order['id']):
                                  print(f"   [DEBUG] ⚠️ FOUND in Global list under symbol: {o['symbol']}")
                    except:
                        pass
                    
            except Exception as e:
                print(f"   [DEBUG] Failed to place dummy order: {e}")

        # Clean symbol for orders (remove :USDT if present)
            # order_sym = sym.split(':')[0] 
            # Revert to using the full symbol from position key as it seemed to work for cancel_all_orders
            order_sym = sym
            
            # Try to resolve to market symbol if possible
            if trader.exchange.markets and sym in trader.exchange.markets:
                print(f"   Symbol {sym} found in markets.")
            else:
                print(f"   Symbol {sym} NOT found in markets. Trying to resolve...")
                found = False
                for m_key, m_val in trader.exchange.markets.items():
                    if m_val['id'] == sym.replace('/', '').replace(':USDT', '') or m_key == sym.split(':')[0]:
                         print(f"   Resolved {sym} -> {m_key}")
                         order_sym = m_key
                         found = True
                         break
                if not found:
                    print(f"   Could not resolve {sym}, using original.")

            print(f"   Using order symbol: {order_sym}")
            
            # Check existing orders
            sl_price = pos.get('sl_price', 0.0)
            tp_price = pos.get('tp_price', 0.0)
            entry_price = float(pos['entry_price'])
            current_price = float(pos['mark_price'])
            amount = float(pos['amount'])
            side = pos['side']
            
            if sl_price > 0 and tp_price > 0:
                print(f"✅ SL/TP already exist for {sym}. SL: {sl_price}, TP: {tp_price}")
                continue
                
            print(f"⚠️ Missing SL/TP for {sym}. Fixing...")
            
            # Calculate Target SL/TP
            if side == 'long':
                target_sl = entry_price * (1 - sl_pct)
                target_tp = entry_price * (1 + tp_pct)
                
                # Check if we should close immediately
                if current_price >= target_tp:
                    print(f"🚀 Price ({current_price}) >= TP ({target_tp}). Taking Profit Immediately!")
                    trader._close_position_by_symbol(order_sym, pos)
                    continue
                elif current_price <= target_sl:
                    print(f"🛑 Price ({current_price}) <= SL ({target_sl}). Stopping Loss Immediately!")
                    trader._close_position_by_symbol(order_sym, pos)
                    continue
                    
                sl_side = 'sell'
                
            else: # short
                target_sl = entry_price * (1 + sl_pct)
                target_tp = entry_price * (1 - tp_pct)
                
                if current_price <= target_tp:
                    print(f"🚀 Price ({current_price}) <= TP ({target_tp}). Taking Profit Immediately!")
                    trader._close_position_by_symbol(order_sym, pos)
                    continue
                elif current_price >= target_sl:
                    print(f"🛑 Price ({current_price}) >= SL ({target_sl}). Stopping Loss Immediately!")
                    trader._close_position_by_symbol(order_sym, pos)
                    continue
                    
                sl_side = 'buy'

            # Place Orders if not closed
            try:
                # DEBUG: Print Full Order Response
                
                # Manual Fetch and Cancel
                print(f"   Fetching open orders for {order_sym}...")
                existing_orders = trader.exchange.fetch_open_orders(order_sym)
                if existing_orders:
                    print(f"   Found {len(existing_orders)} existing orders. Cancelling individually...")
                    for o in existing_orders:
                        print(f"     - Cancelling Order ID: {o['id']} (Type: {o['type']}, Stop: {o.get('stopPrice')})")
                        try:
                            trader.exchange.cancel_order(o['id'], order_sym)
                            print("       ✅ Cancelled.")
                        except Exception as ce:
                            print(f"       ❌ Failed to cancel: {ce}")
                    
                    print("   Waiting 2s...")
                    time.sleep(2)
                else:
                    print("   No existing orders found via fetch_open_orders.")

                # Place SL (STOP_MARKET)
                # Note: Binance Futures SL/TP logic
                # For Long: SL is Sell Stop Market below price. TP is Sell Take Profit Market above price.
                
                # 1. SL
                print(f"   Placing SL at {target_sl:.4f}...")
                try:
                    # Check current price first to avoid immediate trigger
                    ticker = trader.exchange.fetch_ticker(order_sym)
                    current_price = ticker['last']
                    print(f"   [Price Check] Current: {current_price}, SL Target: {target_sl}")
                    
                    if (amount > 0 and target_sl >= current_price) or (amount < 0 and target_sl <= current_price):
                         print("   [WARNING] SL Price might trigger immediately! Adjusting slightly for test if needed or skipping.")
                    
                    sl_order = trader.exchange.create_order(order_sym, 'STOP_MARKET', sl_side, abs(amount), params={
                        'stopPrice': trader.exchange.price_to_precision(order_sym, target_sl),
                        'reduceOnly': True,
                        'workingType': 'MARK_PRICE' # Explicitly set working type
                    })
                    print(f"   >>> SL Order Created. ID: {sl_order['id']}")
                    print(f"   >>> Full Response: {json.dumps(sl_order, default=str)}")
                    
                    # Immediate check with fetch_order
                    time.sleep(2)
                    try:
                        print(f"   >>> Fetching GLOBAL open orders (no symbol filter)...")
                        all_open = trader.exchange.fetch_open_orders()
                        found_global = False
                        for o in all_open:
                            if str(o['id']) == str(sl_order['id']) or (o.get('info', {}).get('algoId') == str(sl_order['id'])):
                                found_global = True
                                print(f"      ✅ MATCH FOUND in Global! Symbol: {o['symbol']}, ID: {o['id']}")
                        
                        if not found_global:
                             print(f"   >>> ❌ Order {sl_order['id']} NOT found in GLOBAL open orders.")
                    except Exception as e:
                        print(f"   >>> ❌ Failed to fetch global orders: {e}")

                    # DEBUG: Try Raw Private API Calls
                    print("   [DEBUG] Trying Raw Private API Calls...")
                    try:
                        raw_symbol = order_sym.replace('/', '').replace(':USDT', '') # SOLUSDT
                        
                        # 1. /fapi/v1/openOrders
                        print(f"   Invoking fapiPrivateGetOpenOrders for {raw_symbol}...")
                        raw_open = trader.exchange.fapiPrivateGetOpenOrders({'symbol': raw_symbol})
                        print(f"   Found {len(raw_open)} raw open orders.")
                        
                        # 2. /fapi/v1/allOrders (History)
                        print(f"   Invoking fapiPrivateGetAllOrders for {raw_symbol} (limit=5)...")
                        raw_history = trader.exchange.fapiPrivateGetAllOrders({'symbol': raw_symbol, 'limit': 5})
                        for o in raw_history:
                             print(f"     Hist Order: ID={o.get('orderId')}, AlgoID={o.get('algoId')}, Type={o.get('type')}, Status={o.get('status')}, WorkingType={o.get('workingType')}")
                             if str(o.get('orderId')) == str(sl_order['id']) or str(o.get('algoId')) == str(sl_order['id']):
                                  print("     ✅ MATCH FOUND in fapiPrivateGetAllOrders!")
                                  print(f"     Full Hist Info: {json.dumps(o, default=str)}")

                        # 3. /fapi/v1/algo/openOrders (Algo)
                        print(f"   Invoking fapiPrivateGetOpenAlgoOrders for {raw_symbol}...")
                        # Note: Endpoint might be fapiPrivateGetAlgoOpenOrders or fapiPrivateGetOpenAlgoOrders depending on CCXT mapping
                        # Based on find_algo_methods.py: fapiPrivateGetOpenAlgoOrders
                        raw_algo = trader.exchange.fapiPrivateGetOpenAlgoOrders({'symbol': raw_symbol}) # or fapiPrivateGetAlgoOpenOrders
                        print(f"   Found {len(raw_algo)} raw algo orders.")
                        for o in raw_algo:
                             print(f"     Algo Order: ID={o.get('orderId')}, AlgoID={o.get('algoId')}, Type={o.get('type')}, Status={o.get('status')}")
                             if str(o.get('algoId')) == str(sl_order['id']):
                                  print("     ✅ MATCH FOUND in fapiPrivateGetOpenAlgoOrders!")
                                  print(f"     Full Algo Info: {json.dumps(o, default=str)}")
                        
                    except Exception as e:
                        print(f"   Failed raw API call: {e}")

                    # Check Trades (Execution)

                    # Check Trades (Execution)
                    print(f"   >>> Checking recent trades for {order_sym}...")
                    try:
                        trades = trader.exchange.fetch_my_trades(order_sym, limit=5)
                        for t in trades:
                            if str(t['order']) == str(sl_order['id']):
                                print(f"   >>> ⚠️ Order EXECUTED immediately! Trade: {t}")
                    except Exception as e:
                        print(f"   >>> Failed to fetch trades: {e}")

                except Exception as e:
                    print(f"   !!! SL Placement Failed: {e}")
                
                # 2. TP
                print(f"   Placing TP at {target_tp:.4f}...")
                try:
                    tp_order = trader.exchange.create_order(order_sym, 'TAKE_PROFIT_MARKET', sl_side, amount, params={
                        'stopPrice': trader.exchange.price_to_precision(order_sym, target_tp),
                        'reduceOnly': True
                    })
                    print(f"   >>> TP Order Result JSON: {json.dumps(tp_order, default=str)}")
        
                    # Immediate check
                    time.sleep(2)
                    print(f"   >>> Fetching recent history for {order_sym}...")
                    try:
                        recent_orders = trader.exchange.fetch_orders(order_sym, limit=10)
                        found = False
                        for o in recent_orders:
                            print(f"      - ID: {o['id']}, Status: {o['status']}, Type: {o['type']}, Side: {o['side']}, Stop: {o.get('stopPrice')}")
                            if str(o['id']) == str(tp_order['id']):
                                found = True
                                print(f"        MATCH FOUND! Info: {o.get('info')}")
                        
                        if not found:
                            print(f"   >>> ❌ Order {tp_order['id']} NOT found in recent history!")
        
                    except Exception as e:
                        print(f"   >>> Failed to fetch history: {e}")
        
                except Exception as e:
                     print(f"   !!! TP Placement Failed: {e}")
                
                print(f"✅ Fixed {order_sym}. New SL: {target_sl:.4f}, New TP: {target_tp:.4f}")
                
            except Exception as e:
                print(f"❌ Failed to place orders for {order_sym}: {e}")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
