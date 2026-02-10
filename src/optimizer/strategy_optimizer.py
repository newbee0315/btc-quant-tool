import pandas as pd
import numpy as np
import logging
import json
import os
import ccxt.pro as ccxt  # Use ccxt.pro or ccxt depending on env, but here standard ccxt is fine for REST
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class StrategyOptimizer:
    def __init__(self, api_key: str, api_secret: str, proxy_url: str = None, config_path: str = "trader_config.json"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.proxy_url = proxy_url
        self.config_path = config_path
        self.report_path = "optimization_report.md"
        
        # Initialize Exchange Connection (Lightweight)
        options = {'defaultType': 'swap'}
        if self.proxy_url:
            options['proxies'] = {
                'http': self.proxy_url,
                'https': self.proxy_url
            }
            
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': options
        })
        
    async def run_analysis(self, days=7):
        """Run full analysis and optimization cycle"""
        logger.info("🤖 Auto-Optimizer: Starting analysis...")
        
        try:
            # 1. Fetch History
            orders = await self.fetch_history(days)
            if not orders:
                logger.warning("No trading history found for analysis.")
                return []
                
            # 2. Analyze Performance
            metrics = self.analyze_performance(orders)
            
            # 3. Diagnose Problems
            problems = self.diagnose_problems(metrics, orders)
            
            # 4. Generate Report
            suggestions = self.suggest_optimizations(metrics, problems)
            self.generate_report(metrics, problems, suggestions)
            
            # 5. Apply Auto-Optimizations (Optional)
            # self.apply_optimizations(suggestions)
            
            logger.info("🤖 Auto-Optimizer: Analysis complete.")
            return suggestions
            
        except Exception as e:
            logger.error(f"Optimizer failed: {e}", exc_info=True)
            return []
        finally:
            await self.exchange.close()

    async def fetch_history(self, days=7) -> List[Dict]:
        """Fetch account trade history"""
        try:
            # Calculate start time
            since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            
            # Load markets to ensure symbols are available
            try:
                await self.exchange.load_markets()
            except Exception as e:
                logger.warning(f"Failed to load markets: {e}")
            
            # Smart symbol selection
            target_symbols = []
            if self.exchange.markets:
                # Select top liquid pairs or just all USDT swap pairs
                # CCXT usually formats swaps as 'BTC/USDT:USDT'
                candidates = [
                    s for s in self.exchange.markets 
                    if (':USDT' in s or '/USDT' in s) and self.exchange.markets[s].get('swap', False)
                ]
                # Prioritize major coins
                majors = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'DOGE/USDT:USDT']
                for m in majors:
                    if m in candidates:
                        target_symbols.append(m)
                    elif m.replace(':USDT', '') in candidates:
                        target_symbols.append(m.replace(':USDT', ''))
                
                # Add a few others if not enough
                for c in candidates:
                    if c not in target_symbols and len(target_symbols) < 8:
                        target_symbols.append(c)
            else:
                # Fallback
                target_symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
            
            logger.info(f"Scanning history for: {target_symbols}")
            
            all_trades = []
            
            for symbol in target_symbols:
                try:
                    # Fetch trades
                    trades = await self.exchange.fetch_my_trades(symbol, since=since)
                    if trades:
                        logger.info(f"Found {len(trades)} trades for {symbol}")
                        all_trades.extend(trades)
                    await asyncio.sleep(0.1) # Rate limit
                except Exception as e:
                    # Symbol might not be valid or no trades
                    # logger.debug(f"No trades or error for {symbol}: {e}")
                    pass
                    
            logger.info(f"Fetched {len(all_trades)} trades from history.")
            return all_trades
        except Exception as e:
            logger.error(f"Error fetching history: {e}")
            return []

    def analyze_performance(self, trades: List[Dict]) -> Dict:
        """Calculate key metrics from trades"""
        if not trades:
            return {}
            
        df = pd.DataFrame(trades)
        
        # Parse PnL from 'info' field for Binance Futures
        # Binance API returns 'realizedPnl' in the info dict
        def get_pnl(row):
            if 'info' in row and isinstance(row['info'], dict):
                return float(row['info'].get('realizedPnl', 0))
            return 0.0
            
        def get_commission(row):
            if 'info' in row and isinstance(row['info'], dict):
                return float(row['info'].get('commission', 0))
            return 0.0

        df['realized_pnl'] = df.apply(get_pnl, axis=1)
        df['commission_val'] = df.apply(get_commission, axis=1)
        df['net_pnl'] = df['realized_pnl'] - df['commission_val']
        
        # Filter only realized PnL events (sometimes trades are just openings)
        # Usually realizedPnl != 0 means a close happened. 
        # But commission is always paid.
        # We want to count "Closed Trades".
        # A trade in CCXT is a fill. A "Round Turn" is hard to reconstruct perfectly without order ID matching.
        # Approximation: Look at fills with realized PnL != 0.
        
        closed_trades = df[df['realized_pnl'] != 0].copy()
        
        total_closed = len(closed_trades)
        total_pnl = df['net_pnl'].sum() # Net PnL includes opening fees too
        
        if total_closed == 0:
            return {
                "total_trades": 0,
                "net_pnl": total_pnl
            }
            
        winning_trades = closed_trades[closed_trades['realized_pnl'] > 0]
        losing_trades = closed_trades[closed_trades['realized_pnl'] < 0]
        
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        win_rate = win_count / total_closed if total_closed > 0 else 0
        
        avg_win = winning_trades['realized_pnl'].mean() if not winning_trades.empty else 0
        avg_loss = losing_trades['realized_pnl'].mean() if not losing_trades.empty else 0
        
        gross_profit = winning_trades['realized_pnl'].sum()
        gross_loss = abs(losing_trades['realized_pnl'].sum())
        
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        return {
            "total_trades": total_closed,
            "net_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss
        }

    def diagnose_problems(self, metrics: Dict, trades: List[Dict]) -> List[str]:
        """Identify issues based on metrics"""
        problems = []
        
        if not metrics:
            return ["No data available for diagnosis."]
            
        win_rate = metrics.get('win_rate', 0)
        profit_factor = metrics.get('profit_factor', 0)
        total_trades = metrics.get('total_trades', 0)
        
        if total_trades < 5:
            problems.append("⚠️ Sample size too small (< 5 trades) for reliable diagnosis.")
            return problems
            
        if win_rate < 0.45:
            problems.append(f"🔴 Low Win Rate ({win_rate*100:.1f}%). Strategy may be entering too early or against trend.")
            
        if profit_factor < 1.1:
            problems.append(f"🔴 Low Profit Factor ({profit_factor:.2f}). Gross Loss is consuming profits.")
            
        if metrics.get('avg_loss', 0) < 0 and metrics.get('avg_win', 0) > 0:
            risk_reward = metrics['avg_win'] / abs(metrics['avg_loss'])
            if risk_reward < 1.0:
                 problems.append(f"🟠 Poor Risk/Reward Ratio ({risk_reward:.2f}). Average loss exceeds average win.")
        
        return problems

    def suggest_optimizations(self, metrics: Dict, problems: List[str]) -> List[str]:
        suggestions = []
        
        if not metrics:
            return []
            
        win_rate = metrics.get('win_rate', 0)
        profit_factor = metrics.get('profit_factor', 0)
        
        # Suggestion Logic
        if win_rate < 0.45:
            suggestions.append("👉 Increase ML Confidence Threshold (e.g., +0.05) to filter weak signals.")
            suggestions.append("👉 Check Trend Filter: Ensure trading only in direction of higher timeframe trend.")
            
        if profit_factor < 1.2:
             suggestions.append("👉 Tighten Stop Loss or Implement Trailing Stop earlier.")
             suggestions.append("👉 Reduce Leverage to minimize slippage impact.")
             
        if not problems:
            suggestions.append("✅ Strategy is performing well. Consider scaling up position size slightly.")
            
        return suggestions

    def generate_report(self, metrics: Dict, problems: List[str], suggestions: List[str]):
        """Write analysis to file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Read existing report if exists to append? 
        # Or just overwrite top section. Let's create a new daily entry style.
        
        report_entry = f"""
# 🤖 Auto-Optimizer Report ({timestamp})

## 📊 Performance Metrics (Last 7 Days)
| Metric | Value |
| :--- | :--- |
| **Total Closed Trades** | {metrics.get('total_trades', 0)} |
| **Net PnL** | `{metrics.get('net_pnl', 0):.2f} USDT` |
| **Win Rate** | **{metrics.get('win_rate', 0)*100:.2f}%** |
| **Profit Factor** | {metrics.get('profit_factor', 0):.2f} |
| **Avg Win** | {metrics.get('avg_win', 0):.2f} USDT |
| **Avg Loss** | {metrics.get('avg_loss', 0):.2f} USDT |

## ⚠️ Diagnosed Problems
"""
        if problems:
            for p in problems:
                report_entry += f"- {p}\n"
        else:
            report_entry += "- ✅ No critical problems detected.\n"
            
        report_entry += "\n## 💡 Optimization Suggestions\n"
        for s in suggestions:
            report_entry += f"- {s}\n"
            
        report_entry += "\n---\n"
        
        try:
            # Prepend to file
            existing_content = ""
            if os.path.exists(self.report_path):
                with open(self.report_path, 'r') as f:
                    existing_content = f.read()
            
            with open(self.report_path, 'w') as f:
                f.write(report_entry + existing_content)
                
            logger.info(f"Report generated: {self.report_path}")
        except Exception as e:
            logger.error(f"Failed to write report: {e}")
