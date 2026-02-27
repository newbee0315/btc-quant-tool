import sys
import os
import unittest
from datetime import datetime
import pandas as pd

# Add project root
sys.path.append(os.getcwd())

from src.strategies.czsc_analyzer import CZSCAnalyzer, CZSC, RawBar, Freq

# Mock Bi class
class MockBi:
    def __init__(self, direction, high, low):
        self.direction = direction # 1 up, -1 down
        self.high = high
        self.low = low

# Mock CZSC object
class MockCZSC:
    def __init__(self, bi_list):
        self.bi_list = bi_list

class TestCZSCLogic(unittest.TestCase):
    def setUp(self):
        self.analyzer = CZSCAnalyzer()
        
    def create_bar(self, i, close, high, low):
        return RawBar(
            symbol="BTCUSDT",
            dt=datetime.now(),
            id=i,
            freq=Freq.F5,
            open=close, # Simplified
            close=close,
            high=high,
            low=low,
            vol=100,
            amount=10000
        )

    def test_third_buy_point(self):
        # Valid 3rd Buy Sequence
        # ZS: Down, Up, Down (Standard ZS)
        # Breakout: Up
        # Pullback: Down (Not entering ZS)
        
        bi_list_valid = [
            MockBi(-1, 108, 102), # -5: Down (ZS 1)
            MockBi(1, 112, 104),  # -4: Up (ZS 2)
            MockBi(-1, 109, 105), # -3: Down (ZS 3)
            # ZS Overlap:
            # d_max = max(102, 104, 105) = 105
            # g_min = min(108, 112, 109) = 108
            # ZS = [105, 108]. ZG = 108.
            
            MockBi(1, 120, 106),  # -2: Breakout (Up). High 120 > 108. Direction 1.
            MockBi(-1, 115, 110)  # -1: Pullback (Down). Low 110 > 108. Direction -1.
        ]
        
        czsc = MockCZSC(bi_list_valid)
        self.assertTrue(self.analyzer._check_third_buy_point(czsc))
        
        # Invalid: Pullback enters ZS
        bi_list_invalid = list(bi_list_valid)
        bi_list_invalid[-1] = MockBi(-1, 115, 107) # Low 107 < 108 (Inside ZS [105, 108])
        czsc_invalid = MockCZSC(bi_list_invalid)
        self.assertFalse(self.analyzer._check_third_buy_point(czsc_invalid))

        # Invalid: Breakout didn't break ZG
        bi_list_no_break = list(bi_list_valid)
        bi_list_no_break[-2] = MockBi(1, 108, 106) # High 108 == 108 (Not > ZG)
        czsc_no_break = MockCZSC(bi_list_no_break)
        self.assertFalse(self.analyzer._check_third_buy_point(czsc_no_break))

    def test_third_sell_point(self):
        # ZS: Up, Down, Up
        # Breakout: Down
        # Pullback: Up
        
        bi_list_valid = [
            MockBi(1, 110, 100),  # -5: Up
            MockBi(-1, 108, 98),  # -4: Down
            MockBi(1, 106, 96),   # -3: Up
            # ZS Overlap:
            # d_max = max(100, 98, 96) = 100 (Wait, d_max is max of LOWs of ZS component strokes?)
            # Standard ZS def: 
            # g_min = min(g1, g2, g3)
            # d_max = max(d1, d2, d3)
            # Here:
            # g1=110, g2=108, g3=106 -> g_min = 106
            # d1=100, d2=98, d3=96 -> d_max = 100
            # ZS = [100, 106]. ZD = 100.
            
            MockBi(-1, 99, 90),   # -2: Breakout (Down). Low 90 < 100. Direction -1.
            MockBi(1, 98, 92)     # -1: Pullback (Up). High 98 < 100. Direction 1.
        ]
        
        czsc = MockCZSC(bi_list_valid)
        self.assertTrue(self.analyzer._check_third_sell_point(czsc))
        
        # Invalid: Pullback enters ZS
        bi_list_invalid = list(bi_list_valid)
        bi_list_invalid[-1] = MockBi(1, 102, 92) # High 102 > 100
        czsc_invalid = MockCZSC(bi_list_invalid)
        self.assertFalse(self.analyzer._check_third_sell_point(czsc_invalid))

if __name__ == '__main__':
    unittest.main()
