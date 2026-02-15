import logging
from src.utils.config_manager import config_manager

logger = logging.getLogger(__name__)

class StrategyOptimizer:
    def __init__(self, trader):
        self.trader = trader

    def optimize(self):
        """
        Analyze performance and tune parameters.
        """
        if not self.trader or not hasattr(self.trader, 'get_stats'):
            logger.warning("StrategyOptimizer: Trader not available or invalid.")
            return

        logger.info("Running Autonomous Strategy Optimization...")
        
        # Get stats
        stats = self.trader.get_stats()
        win_rate = stats.get('win_rate', 0)
        total_pnl = stats.get('total_pnl', 0)
        trades_count = stats.get('total_trades', 0)
        
        # Get current config
        config = config_manager.get_config()
        new_config = config.copy()
        changed = False

        # Logic 1: If Win Rate is low (< 30%) and we have enough trades (> 10), tighten ML threshold
        if trades_count > 10 and win_rate < 30.0:
            current_threshold = config.get('ml_threshold', 0.65)
            if current_threshold < 0.85:
                new_threshold = min(0.85, current_threshold + 0.05)
                new_config['ml_threshold'] = round(new_threshold, 2)
                logger.info(f"Optimization: Low Win Rate ({win_rate}%). Increased ML Threshold to {new_threshold}")
                changed = True

        # Logic 2: High Win Rate (> 60%) and decent volume, relax slightly to catch more moves
        if trades_count > 5 and win_rate > 60.0:
             current_threshold = config.get('ml_threshold', 0.65)
             if current_threshold > 0.55:
                 new_threshold = max(0.55, current_threshold - 0.02)
                 new_config['ml_threshold'] = round(new_threshold, 2)
                 logger.info(f"Optimization: High Win Rate ({win_rate}%). Decreased ML Threshold to {new_threshold} to increase frequency")
                 changed = True
        
        # Logic 3: Drawdown protection
        # If PnL is negative and significant (e.g. < -100u), reduce risk per trade
        if total_pnl < -100: 
             current_risk = config.get('risk_per_trade', 0.02)
             if current_risk > 0.01:
                 new_risk = max(0.01, current_risk - 0.005)
                 new_config['risk_per_trade'] = round(new_risk, 3)
                 logger.info(f"Optimization: Significant Loss ({total_pnl}). Reduced Risk per Trade to {new_risk}")
                 changed = True

        if changed:
            config_manager.update_config(new_config)
            logger.info("Strategy Configuration Updated Successfully.")
        else:
            logger.info("No optimization needed at this time.")

async def run_strategy_optimization(trader):
    optimizer = StrategyOptimizer(trader)
    optimizer.optimize()
