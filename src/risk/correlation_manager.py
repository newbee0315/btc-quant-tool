import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class CorrelationManager:
    """
    Manages correlation risks by analyzing the correlation matrix of asset returns.
    Helps in avoiding homogeneous risk exposure.
    """
    
    def __init__(self, lookback_period: int = 100):
        self.lookback_period = lookback_period
        self.correlation_matrix = pd.DataFrame()
        self.price_history: Dict[str, pd.Series] = {}
        
    def update_price_history(self, symbol: str, prices: pd.Series):
        """Update price history for a symbol."""
        # Ensure prices are sorted by time and take the last N periods
        if not prices.empty:
            self.price_history[symbol] = prices.tail(self.lookback_period)
            
    def calculate_correlation_matrix(self):
        """Calculate the correlation matrix based on stored price histories."""
        if len(self.price_history) < 2:
            return
            
        # Combine all price series into a DataFrame
        # Align by index (timestamp)
        df = pd.DataFrame(self.price_history)
        
        # Calculate percentage returns
        returns = df.pct_change()
        
        # Calculate correlation matrix
        self.correlation_matrix = returns.corr()
        logger.info(f"Updated Correlation Matrix for {len(self.correlation_matrix)} assets.")
        
    def get_correlation(self, symbol_a: str, symbol_b: str) -> float:
        """Get correlation coefficient between two symbols."""
        if self.correlation_matrix.empty:
            return 0.0
            
        if symbol_a in self.correlation_matrix.index and symbol_b in self.correlation_matrix.columns:
            return self.correlation_matrix.loc[symbol_a, symbol_b]
            
        return 0.0
        
    def check_portfolio_correlation(self, new_symbol: str, current_positions: List[str], threshold: float = 0.7) -> bool:
        """
        Check if the new symbol is highly correlated with any currently held position.
        Returns True if correlation risk is acceptable (low correlation).
        Returns False if correlation is too high with any existing position.
        """
        if self.correlation_matrix.empty:
            return True
            
        if new_symbol not in self.correlation_matrix.index:
            # If we don't have data for the new symbol, assume it's safe (or unsafe, depending on policy)
            # Here we assume safe to avoid blocking trading due to missing history
            return True
            
        for held_symbol in current_positions:
            if held_symbol == new_symbol:
                continue
                
            if held_symbol in self.correlation_matrix.index:
                corr = self.correlation_matrix.loc[new_symbol, held_symbol]
                if corr > threshold:
                    logger.warning(f"Correlation Risk: {new_symbol} vs {held_symbol} = {corr:.2f} > {threshold}")
                    return False
                    
        return True
