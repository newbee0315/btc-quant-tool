import json
import os
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_path="config/strategy_config.json"):
        # Make path absolute
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.config_path = os.path.join(base_dir, config_path)
        self.config = self._load_config()

    def _ensure_dir(self):
        if not os.path.exists(os.path.dirname(self.config_path)):
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

    def _load_config(self):
        self._ensure_dir()
        if not os.path.exists(self.config_path):
            default_config = {
                "ml_threshold": 0.60,
                "rsi_period": 14,
                "ema_period": 200,
                "leverage": 10,
                "sl_pct": 0.02,
                "tp_pct": 0.06,
                "trailing_stop_trigger_pct": 0.01,
                "trailing_stop_lock_pct": 0.02,
                "risk_per_trade": 0.02,
                "max_drawdown_limit": 0.10
            }
            self.save_config(default_config)
            return default_config
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def get_config(self):
        # Reload to ensure freshness if modified externally
        self.config = self._load_config()
        return self.config

    def update_config(self, new_config: dict):
        self.config.update(new_config)
        self.save_config(self.config)

    def save_config(self, config: dict):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

config_manager = ConfigManager()
