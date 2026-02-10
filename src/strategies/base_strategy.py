from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any

class BaseStrategy(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def analyze(self, df: pd.DataFrame, extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Analyze market data and return signal.
        
        Args:
            df: OHLCV DataFrame
            extra_data: Additional data like ML predictions, account balance, etc.
            
        Returns:
            Dict containing:
            - signal: 1 (Buy), -1 (Sell), 0 (Hold)
            - reason: str explanation
            - stop_loss: float (optional)
            - take_profit: float (optional)
            - indicators: Dict of calculated indicators
        """
        pass
