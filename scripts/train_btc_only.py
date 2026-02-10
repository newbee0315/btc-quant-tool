import sys
import os
sys.path.append(os.getcwd())

from src.models.train_multicoin import train_for_symbol
import logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    print("Training BTCUSDT model...")
    train_for_symbol("BTCUSDT")
    print("Done.")
