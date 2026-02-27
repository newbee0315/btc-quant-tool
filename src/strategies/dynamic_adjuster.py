import logging
from typing import Dict, Any
from src.utils.config_manager import config_manager

logger = logging.getLogger(__name__)

class DynamicConfigAdjuster:
    """
    Dynamically adjusts strategy configuration based on:
    1. Account Equity (Micro vs Large)
    2. Market Regime (Volatile vs Stable)
    3. Recent Performance (Drawdown vs Profit)
    """
    
    def __init__(self):
        self.config_manager = config_manager
        
    def adjust(self, current_equity: float, market_regime: str, recent_drawdown_pct: float = 0.0) -> Dict[str, Any]:
        """
        Calculate and apply new configuration based on inputs.
        
        Args:
            current_equity: Total account value in USDT.
            market_regime: 'trending', 'ranging', 'volatile', or 'uncertain'.
            recent_drawdown_pct: Current daily drawdown percentage (0.0 to 1.0).
            
        Returns:
            Dict containing the updated configuration parameters.
        """
        if current_equity <= 0:
            logger.warning("Invalid equity for adjustment. Skipping.")
            return {}

        # 1. Base Mode based on Equity (Growth Phase)
        # Goal: Aggressive growth for small accounts, preservation for large.
        base_config = {}
        
        if current_equity < 1000:
            # Phase 1: Micro Account (< 1000U) -> Aggressive Growth
            # "Escape Velocity" Mode
            base_config = {
                "leverage": 10,
                "max_portfolio_leverage": 20,
                "risk_per_trade": 0.05,  # 5% risk per trade to compound fast
                "ml_threshold": 0.60,    # Loose threshold for more frequency
                "sl_pct": 0.02,          # Standard 2%
                "tp_pct": 0.06           # Standard 6%
            }
            mode_name = "🚀 Micro Growth (Aggressive)"
            
        elif 1000 <= current_equity < 5000:
            # Phase 2: Small Account (1k - 5k) -> Balanced Growth
            base_config = {
                "leverage": 8,
                "max_portfolio_leverage": 15,
                "risk_per_trade": 0.03,  # 3% risk
                "ml_threshold": 0.65,    # Balanced threshold
                "sl_pct": 0.02,
                "tp_pct": 0.05
            }
            mode_name = "📈 Balanced Growth"
            
        else:
            # Phase 3: Medium Account (> 5k) -> Capital Preservation
            base_config = {
                "leverage": 5,
                "max_portfolio_leverage": 10,
                "risk_per_trade": 0.02,  # 2% risk (Standard)
                "ml_threshold": 0.70,    # Strict threshold
                "sl_pct": 0.015,         # Tighter SL
                "tp_pct": 0.04           # Conservative TP
            }
            mode_name = "🛡️ Capital Preservation"

        # 2. Market Regime Modifiers
        # Override base config based on market conditions
        
        if market_regime == "volatile":
            # High Volatility -> Defense Mode
            # Reduce leverage and risk, tighten ML threshold
            base_config["leverage"] = min(base_config["leverage"], 5)
            base_config["max_portfolio_leverage"] = min(base_config["max_portfolio_leverage"], 8)
            base_config["risk_per_trade"] = max(0.01, base_config["risk_per_trade"] * 0.5) # Half risk
            base_config["ml_threshold"] = max(base_config["ml_threshold"], 0.75) # Very strict
            mode_name += " + 🌪️ Volatile Defense"
            
        elif market_regime == "ranging":
            # Ranging -> Scalping Mode
            # Increase frequency, tight SL/TP
            base_config["ml_threshold"] = 0.55 # Very loose for scalping
            base_config["sl_pct"] = 0.01
            base_config["tp_pct"] = 0.015
            mode_name += " + 🦀 Scalping"
            
        elif market_regime == "trending":
            # Trending -> Trend Following
            # Let winners run
            base_config["tp_pct"] = 0.08 # Extend TP
            mode_name += " + 🌊 Trend Following"

        # 3. Drawdown Brake
        # If daily drawdown is high, force safety
        if recent_drawdown_pct > 0.05: # > 5% drawdown
            logger.warning(f"⚠️ High Drawdown ({recent_drawdown_pct*100:.1f}%) detected! Enforcing Safety Mode.")
            base_config["leverage"] = 3
            base_config["risk_per_trade"] = 0.01
            base_config["ml_threshold"] = 0.80
            mode_name = "🚑 Emergency Safety (High Drawdown)"

        # Apply Configuration
        logger.info(f"🔄 Dynamic Adjustment: Equity=${current_equity:.1f} | Regime={market_regime} | Mode: {mode_name}")
        
        # Only update if changed? 
        # For simplicity, we update and let config_manager handle saving if needed.
        # But to avoid disk I/O spam, we should check diff.
        # ConfigManager.update_config handles merge.
        
        current_conf = self.config_manager.get_config()
        needs_update = False
        for k, v in base_config.items():
            if current_conf.get(k) != v:
                needs_update = True
                break
        
        if needs_update:
            self.config_manager.update_config(base_config)
            logger.info(f"✅ Strategy Config Updated: {base_config}")
            return base_config
        else:
            # logger.info("Config stable. No changes.")
            return {}

dynamic_adjuster = DynamicConfigAdjuster()
