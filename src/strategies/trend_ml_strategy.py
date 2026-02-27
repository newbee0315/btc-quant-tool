import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any
from .base_strategy import BaseStrategy
from .czsc_analyzer import create_czsc_analyzer
from src.analysis.regime import MarketRegimeClassifier, MarketRegime

from czsc import Freq

class TrendMLStrategy(BaseStrategy):
    """
    A hybrid strategy combining Technical Analysis (Trend Following) with Machine Learning.
    Inspired by popular open-source crypto bots (e.g., Binance-Futures-Trading-Bot).
    
    Logic:
    1. Trend Filter: EMA 200. Long if Price > EMA200, Short if Price < EMA200.
    2. Momentum Filter: RSI (14). Long if RSI < 70, Short if RSI > 30.
    3. ML Confirmation: Only enter if ML Model predicts high probability (> threshold).
    4. CZSC Filter (Optional): Use Chanlun patterns (Fenxing, Bi, Divergence) to confirm entries.
    """
    
    def __init__(self, ema_period: int = 200, rsi_period: int = 14, ml_threshold: float = 0.60, atr_period: int = 14, enable_czsc: bool = True):
        super().__init__("TrendMLStrategy")
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.ml_threshold = ml_threshold
        self.atr_period = atr_period
        self.enable_czsc = enable_czsc
        self.logs = []  # Buffer to store strategy execution logs
        
        # CZSC 缠论分析器 (多时间级别)
        if self.enable_czsc:
            self.czsc_analyzer_5m = create_czsc_analyzer(freq="5min")
            self.czsc_analyzer_30m = create_czsc_analyzer(freq="30min")
            self.czsc_analyzer_1h = create_czsc_analyzer(freq="60min")

    def _get_chan_bullish_signal(self, chan_analysis_5m: Dict[str, Any], chan_analysis_30m: Dict[str, Any]) -> bool:
        """获取缠论多头信号"""
        # 简化的多头信号逻辑
        # 实际应用中应该基于分型、笔、中枢等结构进行复杂判断
        
        # 检查底分型
        if chan_analysis_5m['fenxing'].get('has_fenxing', False) and \
           chan_analysis_5m['fenxing'].get('type') == '底分型':
            return True
        
        # 检查向上笔
        if chan_analysis_5m['bi'].get('has_bi', False) and \
           chan_analysis_5m['bi'].get('direction') == '向上笔':
            return True
            
        # 多时间级别确认
        if chan_analysis_30m['fenxing'].get('has_fenxing', False) and \
           chan_analysis_30m['fenxing'].get('type') == '底分型':
            return True
            
        return False
    
    def _get_chan_bearish_signal(self, chan_analysis_5m: Dict[str, Any], chan_analysis_30m: Dict[str, Any]) -> bool:
        """获取缠论空头信号"""
        # 检查顶分型
        if chan_analysis_5m['fenxing'].get('has_fenxing', False) and \
           chan_analysis_5m['fenxing'].get('type') == '顶分型':
            return True
        
        # 检查向下笔
        if chan_analysis_5m['bi'].get('has_bi', False) and \
           chan_analysis_5m['bi'].get('direction') == '向下笔':
            return True
            
        # 多时间级别确认
        if chan_analysis_30m['fenxing'].get('has_fenxing', False) and \
           chan_analysis_30m['fenxing'].get('type') == '顶分型':
            return True
            
        return False
    
    def _get_consolidation_signal(self, chan_analysis: Dict[str, Any]) -> bool:
        """获取中枢整理信号"""
        # 检查中枢是否存在
        if chan_analysis['zs'].get('has_zs', False):
            # 中枢范围较小，表明整理状态
            zs_range_pct = chan_analysis['zs'].get('range_pct', 0)
            if zs_range_pct < 2.0:  # 中枢范围小于2%
                return True
        return False

    def log_execution(self, timestamp, close_price, ema_trend, rsi, ml_prob, signal, reasons, sl=0, tp=0, macd=0, macd_signal=0, macd_hist=0):
        """Buffer execution log"""
        log_entry = {
            "timestamp": timestamp,
            "close": round(close_price, 2),
            "ema": round(ema_trend, 2),
            "rsi": round(rsi, 2),
            "ml_prob": round(ml_prob, 3),
            "signal": signal,
            "reasons": reasons,
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "macd": round(macd, 2),
            "macd_signal": round(macd_signal, 2),
            "macd_hist": round(macd_hist, 2)
        }
        self.logs.insert(0, log_entry)
        if len(self.logs) > 50:  # Keep last 50 entries
            self.logs.pop()

    def get_logs(self):
        return self.logs

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Calculate Heikin Ashi Candles
        # HA_Close = (Open + High + Low + Close) / 4
        # HA_Open = (Previous HA_Open + Previous HA_Close) / 2
        
        df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        
        # Initialize ha_open with standard open
        ha_open = [df['open'].iloc[0]]
        for i in range(1, len(df)):
            ha_open.append((ha_open[-1] + df['ha_close'].iloc[i-1]) / 2)
        df['ha_open'] = ha_open
        
        df['ha_high'] = df[['high', 'ha_open', 'ha_close']].max(axis=1)
        df['ha_low'] = df[['low', 'ha_open', 'ha_close']].min(axis=1)
        
        # Calculate EMA 200 (Trend)
        df['ema_trend'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()
        
        # Calculate EMA 50 (Fast Trend for confirmation)
        df['ema_fast'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Calculate MACD
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp12 - exp26
        df['signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['histogram'] = df['macd'] - df['signal_line']
        
        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(self.atr_period).mean()

        # Calculate ADX (14) - Simplified using EMA
        # +DM and -DM
        up = df['high'] - df['high'].shift(1)
        down = df['low'].shift(1) - df['low']
        
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        
        # Smooth DM and TR using EMA (Wilder's smoothing approx alpha=1/14)
        alpha = 1.0 / 14.0
        df['_tr_smooth'] = true_range.ewm(alpha=alpha, adjust=False).mean()
        df['_plus_dm_smooth'] = pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()
        df['_minus_dm_smooth'] = pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()
        
        # Calculate DI
        df['plus_di'] = 100 * (df['_plus_dm_smooth'] / df['_tr_smooth'])
        df['minus_di'] = 100 * (df['_minus_dm_smooth'] / df['_tr_smooth'])
        
        # Calculate DX and ADX
        dx = 100 * np.abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
        df['adx'] = dx.ewm(alpha=alpha, adjust=False).mean()

        
        # Calculate Volume MA (20)
        df['vol_ma'] = df['volume'].rolling(window=20).mean()
        
        # Calculate Taker Buy/Sell Ratio (Flow)
        if 'taker_buy_volume' in df.columns:
            # Taker Buy Ratio = Taker Buy Vol / Taker Sell Vol
            # Taker Sell Vol = Total Vol - Taker Buy Vol
            taker_sell_vol = df['volume'] - df['taker_buy_volume']
            # Avoid division by zero
            taker_sell_vol = taker_sell_vol.replace(0, 0.0001)
            df['taker_buy_ratio'] = df['taker_buy_volume'] / taker_sell_vol
        else:
            df['taker_buy_ratio'] = 1.0 # Neutral default

        # Calculate Volatility Metrics for Multi-Mode
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=20).std()
        df['atr_ma'] = df['atr'].rolling(window=50).mean()
        
        # CZSC 缠论分析 - 使用完整的CZSC库进行分析
        # 分析结果将在get_signal方法中使用
        if self.enable_czsc:
            # 初始化信号列
            df['czsc_bullish'] = False
            df['czsc_bearish'] = False
            
            # 重置分析器状态 (确保回测独立性)
            self.czsc_analyzer_5m.czsc_objects = {}
            
            # 将 df 转换为 RawBar 列表
            # 注意：这里假设 df 的频率与分析器频率匹配或兼容
            bars = self.czsc_analyzer_5m.convert_to_raw_bars(df, "BACKTEST")
            rsi_values = df['rsi'].fillna(50).values
            
            czsc_bullish_list = []
            czsc_bearish_list = []
            czsc_details_list = []
            
            for i, bar in enumerate(bars):
                # 更新分析器
                self.czsc_analyzer_5m.update_one_bar(bar)
                
                # 获取结果
                res = self.czsc_analyzer_5m.get_analysis_result("BACKTEST")
                current_rsi = rsi_values[i]
                
                # 检查缠论买点 (一买、二买、三买)
                is_bullish = False
                details = []
                tp = res.get('trade_points', {})
                
                if tp.get('first_buy'): 
                    is_bullish = True
                    details.append("一买")
                if tp.get('second_buy'): 
                    is_bullish = True
                    details.append("二买")
                if tp.get('third_buy'): 
                    is_bullish = True
                    details.append("三买")
                
                # 保留原有的底背驰检查作为补充 (因为一买就是底背驰，这里可能重复但无害)
                if res['divergence']['has_divergence'] and res['divergence']['type'] == '底背驰':
                    is_bullish = True
                    details.append("底背驰")
                elif res['fenxing']['has_fenxing'] and res['fenxing']['type'] == '底分型':
                    # 只有底分型可能不够强，结合 RSI (更严格: < 30)
                    if current_rsi < 30: 
                         is_bullish = True
                         details.append("底分型+超卖")
                
                # 检查缠论卖点 (一卖、二卖、三卖)
                is_bearish = False
                if tp.get('first_sell'): 
                    is_bearish = True
                    details.append("一卖")
                if tp.get('second_sell'): 
                    is_bearish = True
                    details.append("二卖")
                if tp.get('third_sell'): 
                    is_bearish = True
                    details.append("三卖")
                
                if res['divergence']['has_divergence'] and res['divergence']['type'] == '顶背驰':
                    is_bearish = True
                    details.append("顶背驰")
                elif res['fenxing']['has_fenxing'] and res['fenxing']['type'] == '顶分型':
                     if current_rsi > 70:
                         is_bearish = True
                         details.append("顶分型+超买")
                    
                czsc_bullish_list.append(is_bullish)
                czsc_bearish_list.append(is_bearish)
                czsc_details_list.append(",".join(details))
                
            df['czsc_bullish'] = czsc_bullish_list
            df['czsc_bearish'] = czsc_bearish_list
            df['czsc_details'] = czsc_details_list


        
        return df

    def get_signal(self, row, prev_row, extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate signal from a single row of data (with indicators pre-calculated).
        Requires prev_row for trend change detection (e.g. MACD histogram slope).
        """
        close_price = row['close']
        ha_close = row['ha_close']
        ha_open = row['ha_open']
        ema_trend = row['ema_trend']
        ema_fast = row.get('ema_fast', 0)
        rsi = row['rsi']
        atr = row.get('atr', 0)
        adx = row.get('adx', 0)
        atr_ma = row.get('atr_ma', atr)
        volatility = row.get('volatility', 0)
        
        macd = row.get('macd', 0)
        macd_signal = row.get('signal_line', 0)
        macd_hist = row['histogram']
        prev_macd_hist = prev_row['histogram']
        volume = row['volume']
        vol_ma = row.get('vol_ma', 0)
        
        # Determine Market Mode
        market_mode = "normal"
        
        # Use Regime Classifier result if available
        if extra_data and 'market_regime' in extra_data:
            regime = extra_data['market_regime']
            if regime == MarketRegime.RANGING.value:
                market_mode = "low"
            elif regime == MarketRegime.VOLATILE.value:
                market_mode = "high"
            elif regime == MarketRegime.TRENDING.value:
                market_mode = "normal" # Standard Trend Mode
        else:
            # Fallback to old logic
            if atr < (atr_ma * 0.7) and volatility < 0.008:
                market_mode = "low"
            elif atr > (atr_ma * 1.3) or volatility > 0.015:
                market_mode = "high"
            
        # 2. Get ML Prediction (Multi-Horizon Consensus)
        ml_prob = 0.5
        ml_prob_10m = 0.5
        
        if extra_data:
            # 30m Prediction (Primary)
            if 'ml_prediction' in extra_data:
                pred = extra_data['ml_prediction']
                if isinstance(pred, dict):
                    ml_prob = pred.get('probability', 0.5)
                else:
                    ml_prob = float(pred)
            
            # 10m Prediction (Secondary/Confirmation)
            if 'ml_prediction_10m' in extra_data:
                pred10 = extra_data['ml_prediction_10m']
                if isinstance(pred10, dict):
                    ml_prob_10m = pred10.get('probability', 0.5)
                else:
                    ml_prob_10m = float(pred10)

        # 3. Generate Signal
        signal = 0
        reason = []
        
        # Trend & Volume Strength
        is_strong_uptrend = ema_fast > ema_trend
        is_strong_downtrend = ema_fast < ema_trend
        is_volume_support = volume > vol_ma
        
        # Heikin Ashi Trend
        is_ha_bullish = ha_close > ha_open
        is_ha_bearish = ha_close < ha_open
        
        # ML Consensus (Adaptive Threshold)
        # Optimized: Use configured threshold (0.60) as base, adjust for market conditions
        effective_threshold = self.ml_threshold
        
        if market_mode == 'low': effective_threshold = min(0.80, self.ml_threshold + 0.10)
        if market_mode == 'high': effective_threshold = max(0.55, self.ml_threshold - 0.05)
        
        is_ml_bullish = ml_prob >= effective_threshold
        is_ml_bearish = ml_prob <= (1 - effective_threshold)
        
        # Secondary confirmation (looser threshold, e.g. > 0.55 for bull, < 0.45 for bear)
        is_ml10_bullish = ml_prob_10m > 0.55
        is_ml10_bearish = ml_prob_10m < 0.45
        
        # CZSC 缠论模式识别 (第四信号组件)
        is_chan_bullish = False
        is_chan_bearish = False
        is_consolidation = False
        
        if self.enable_czsc:
            is_chan_bullish = row.get('czsc_bullish', False)
            is_chan_bearish = row.get('czsc_bearish', False)
            
        # Long Logic
        # Use HA Close for smoother trend check
        # Aggressive: Allow 0.5% buffer below EMA
        is_uptrend = ha_close > (ema_trend * 0.995) 
        is_rsi_safe_long = rsi < 80 # Relaxed from 75
        is_strong_adx = adx > 10 # Relaxed from 15 for more signals
        is_macd_bullish = macd_hist > 0 and macd_hist > prev_macd_hist
        
        # High Frequency Scalping Mode (Low Volatility)
        is_scalp_long = False
        is_scalp_short = False
        
        # [Phase 1] Data Depth & Flow Analysis
        obi = 0.0
        if extra_data and 'order_book' in extra_data:
            ob = extra_data['order_book']
            bids = ob.get('bids', [])
            asks = ob.get('asks', [])
            if bids and asks:
                # Top 5 levels depth
                bid_qty = sum([float(b[1]) for b in bids[:5]])
                ask_qty = sum([float(a[1]) for a in asks[:5]])
                if bid_qty + ask_qty > 0:
                    obi = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        
        taker_buy_ratio = row.get('taker_buy_ratio', 1.0)
        
        if market_mode == 'low':
            # In low volatility, we scalp small moves
            # Conditions:
            # 1. HA Candle is Green (Bullish)
            # 2. RSI is not overbought (< 70)
            # 3. Price is above Fast EMA (50)
            # 4. ML is neutral or bullish (> 0.45)
            # 5. [New] OBI > 0.1 (More bids than asks)
            # 6. [New] Taker Buy Ratio > 1.05 (More buying pressure)
            
            if is_ha_bullish and rsi < 70 and ha_close > ema_fast and ml_prob > 0.45:
                # Check Flow and Depth
                if obi > 0.1 and taker_buy_ratio > 1.05:
                    is_scalp_long = True
            
            # Scalp Short
            if is_ha_bearish and rsi > 30 and ha_close < ema_fast and ml_prob < 0.55:
                 if obi < -0.1 and taker_buy_ratio < 0.95:
                     is_scalp_short = True
                
        # 缠论增强: 底分型确认或中枢突破
        is_chan_confirmed_long = False
        if self.enable_czsc:
            is_chan_confirmed_long = is_chan_bullish
        
        # 缠论信号过滤条件:
        # 如果启用缠论，仅靠缠论信号入场需要有成交量支持，或者与ML共振
        # 纯缠论信号: (is_chan_confirmed_long and is_volume_support)
        # 混合信号: (is_ml_bullish or (is_chan_confirmed_long and is_volume_support))
        
        should_enter_long = is_ml_bullish
        if is_chan_confirmed_long and is_volume_support:
             should_enter_long = True
        
        # Enable entry if Scalping Mode is active
        if is_scalp_long:
            should_enter_long = True
        
        # Standard Trend Logic
        # CZSC Filter: Don't enter Long if CZSC is Bearish (Top Divergence/Sell Point)
        if self.enable_czsc and is_chan_bearish and not is_scalp_long:
             should_enter_long = False

        if (is_uptrend or is_scalp_long) and is_ha_bullish and is_rsi_safe_long and (is_macd_bullish or is_scalp_long) and should_enter_long and is_strong_adx:
            signal = 1
            if is_scalp_long:
                reason.append(f"[Scalp] LowVol+HA_Bullish")
                reason.append(f"OBI({obi:.2f})>0.1")
                reason.append(f"Flow({taker_buy_ratio:.2f})>1.05")
            else:
                reason.append(f"HA价格>EMA200")
            
            reason.append(f"HA阳线")
            reason.append(f"ADX>10")
            reason.append(f"RSI({rsi:.1f})<80")
            
            if is_macd_bullish:
                reason.append(f"MACD金叉增强")
            if is_ml_bullish:
                reason.append(f"ML30m({ml_prob:.2f})>=Threshold")
            if is_chan_confirmed_long:
                reason.append(f"缠论买点+放量确认")
            if is_ml10_bullish:
                reason.append(f"ML10m({ml_prob_10m:.2f})确认")
        
        # CZSC Reversal Logic (Bypass EMA Trend)
        elif self.enable_czsc and is_chan_confirmed_long and is_volume_support and is_ha_bullish and is_rsi_safe_long:
            # Parameter Tuning: Stricter ML confirmation for reversals (was 0.65)
            if ml_prob > 0.70: 
                signal = 1
                reason.append(f"缠论底背驰/分型反转")
                reason.append(f"放量确认")
                reason.append(f"HA阳线")
                reason.append(f"ML确认({ml_prob:.2f})>0.7")
        
        # Short Logic
        # Aggressive: Allow 0.5% buffer above EMA
        is_downtrend = ha_close < (ema_trend * 1.005)
        is_rsi_safe_short = rsi > 20 # Relaxed from 25
        is_macd_bearish = macd_hist < 0 and macd_hist < prev_macd_hist
        
        # 缠论增强: 顶分型确认或中枢跌破
        is_chan_confirmed_short = False
        if self.enable_czsc:
            is_chan_confirmed_short = is_chan_bearish
            
        should_enter_short = is_ml_bearish
        if is_chan_confirmed_short and is_volume_support:
             should_enter_short = True
        
        if is_scalp_short:
             should_enter_short = True
        
        # CZSC Filter: Don't enter Short if CZSC is Bullish (Bottom Divergence/Buy Point)
        if self.enable_czsc and is_chan_bullish and not is_scalp_short:
             should_enter_short = False

        if (is_downtrend or is_scalp_short) and is_ha_bearish and is_rsi_safe_short and (is_macd_bearish or is_scalp_short) and should_enter_short and is_strong_adx:
            signal = -1
            if is_scalp_short:
                reason.append(f"[Scalp] LowVol+HA_Bearish")
                reason.append(f"OBI({obi:.2f})<-0.1")
                reason.append(f"Flow({taker_buy_ratio:.2f})<0.95")
            else:
                reason.append(f"HA价格<EMA200")
            reason.append(f"HA阴线")
            reason.append(f"ADX>20")
            reason.append(f"RSI({rsi:.1f})>30")
            reason.append(f"MACD死叉增强")
            if is_ml_bearish:
                reason.append(f"ML30m({ml_prob:.2f})<=Threshold")
            if is_chan_confirmed_short:
                reason.append(f"缠论卖点+放量确认")
            if is_ml10_bearish:
                reason.append(f"ML10m({ml_prob_10m:.2f})确认")
        
        # CZSC Reversal Logic (Bypass EMA Trend)
        elif self.enable_czsc and is_chan_confirmed_short and is_volume_support and is_ha_bearish and is_rsi_safe_short:
            # Parameter Tuning: Stricter ML confirmation for reversals (was 0.35)
            if ml_prob < 0.30: 
                signal = -1
                reason.append(f"缠论顶背驰/分型反转")
                reason.append(f"放量确认")
                reason.append(f"HA阴线")
                reason.append(f"ML确认({ml_prob:.2f})<0.3")


        # -----------------------------------------------------------
        # High Frequency Scalping Mode (DISABLED for Strict Strategy Adherence)
        # -----------------------------------------------------------
        # if signal == 0:
        #     # Scalp Long
        #     is_scalp_trend_up = ha_close > ema_fast
        #     is_ml10_strong_bull = ml_prob_10m >= 0.75 # Was 0.60
        #     is_rsi_scalp_long = rsi < 75
            
        #     czsc_filter_pass_long = True
        #     if self.enable_czsc and is_chan_bearish:
        #          czsc_filter_pass_long = False 
            
        #     if is_scalp_trend_up and is_ml10_strong_bull and is_rsi_scalp_long and is_volume_support and czsc_filter_pass_long:
        #         signal = 1
        #         reason.append(f"[Scalp]HA>EMA50")
        #         reason.append(f"ML10m({ml_prob_10m:.2f})>=0.75")
        #         reason.append(f"Vol>MA")
        #         reason.append(f"RSI({rsi:.1f})")

        #     # Scalp Short
        #     is_scalp_trend_down = ha_close < ema_fast
        #     is_ml10_strong_bear = ml_prob_10m <= 0.25 # Was 0.40
        #     is_rsi_scalp_short = rsi > 25
            
        #     czsc_filter_pass_short = True
        #     if self.enable_czsc and is_chan_bullish:
        #          czsc_filter_pass_short = False
            
        #     if is_scalp_trend_down and is_ml10_strong_bear and is_rsi_scalp_short and is_volume_support and czsc_filter_pass_short:
        #         signal = -1
        #         reason.append(f"[Scalp]HA<EMA50")
        #         reason.append(f"ML10m({ml_prob_10m:.2f})<=0.25")
        #         reason.append(f"Vol>MA")
        #         reason.append(f"RSI({rsi:.1f})")
        
        # If no signal, add reasons for why (for debugging/transparency)
        if signal == 0:
            if not is_ml_bullish and not is_ml_bearish:
                reason.append(f"ML置信度不足({ml_prob:.2f})")
            elif is_ml_bullish and not is_uptrend:
                reason.append(f"ML看多但趋势不符(HA<EMA)")
            elif is_ml_bearish and not is_downtrend:
                reason.append(f"ML看空但趋势不符(HA>EMA)")
            elif is_ml_bullish and not is_macd_bullish:
                reason.append(f"ML看多但MACD未确认")
            elif is_ml_bearish and not is_macd_bearish:
                reason.append(f"ML看空但MACD未确认")
            else:
                reason.append("观望中")


        # 4. Multi-Mode Risk Management (Risk-Based Position Sizing)
        sl_price = 0.0
        tp_price = 0.0
        # Dynamic Leverage Calculation (Respect global cap 10x; PM caps to 8x on high confidence)
        suggested_leverage = 5.0
        if market_mode == 'high' or ml_prob > 0.8:
             suggested_leverage = 8.0
             
        position_size = 0.0
        
        if signal != 0 and atr > 0:
            total_capital = extra_data.get('total_capital', 10.0) if extra_data else 10.0
            
            # Risk Parameters
            # User Requirement: 
            # 1. Trend Mode: Risk-Reward 1:3, 2% Hard Stop Loss
            # 2. Scalp Mode: High Frequency (Tighter SL/TP)
            
            if market_mode == 'low' or '[Scalp]' in str(reason):
                # Scalping Mode (High Frequency)
                # SL 1%, TP 1.5% (R:R 1.5)
                sl_pct = 0.01
                tp_pct = 0.015
                
                sl_dist = close_price * sl_pct
                tp_dist = close_price * tp_pct
                
                # Add log
                reason.append(f"Risk:Scalp(SL{sl_pct*100}%/TP{tp_pct*100}%)")
            else:
                # Trend Mode (Normal/High Volatility)
                # SL 2% (Hard), TP 6% (Target 1:3)
                sl_pct = 0.02
                tp_pct = 0.06
                
                # Dynamic adjustment for High Volatility?
                # User said "2% hard stop-loss", so we stick to 2%.
                
                sl_dist = close_price * sl_pct
                tp_dist = close_price * tp_pct
                
                reason.append(f"Risk:Trend(SL{sl_pct*100}%/TP{tp_pct*100}%)")

            if signal == 1:
                sl_price = close_price - sl_dist
                tp_price = close_price + tp_dist
            else:
                sl_price = close_price + sl_dist
                tp_price = close_price - tp_dist
                
            reason.append(f"模式:{market_mode}")
            reason.append(f"杠杆:{int(suggested_leverage)}x")

        entry_style = "smart"
        grid_levels = 0
        grid_spacing_pct = 0.0
        grid_wait_s = 0
        try:
            if signal != 0 and market_mode == 'low' and close_price > 0:
                entry_style = "grid"
                grid_levels = 3
                raw_spacing = float(atr / close_price) * 0.5 if atr and close_price else 0.0015
                grid_spacing_pct = max(0.001, min(0.003, raw_spacing))
                grid_wait_s = 6
        except Exception:
            pass

        # Log execution
        self.log_execution(
            timestamp=datetime.now().isoformat(),
            close_price=close_price,
            ema_trend=ema_trend,
            rsi=rsi,
            ml_prob=ml_prob,
            signal=signal,
            reasons=reason,
            sl=sl_price,
            tp=tp_price,
            macd=macd,
            macd_signal=macd_signal,
            macd_hist=macd_hist
        )

        return {
            "signal": signal,
            "reason": ", ".join(reason) if reason else "No signal",
            "indicators": {
                "ema": ema_trend,
                "rsi": rsi,
                "atr": atr,
                "ml_prob": ml_prob,
                "macd_hist": macd_hist,
                "adx": adx,
                "czsc_details": row.get('czsc_details', "")
            },
            "trade_params": {
                "sl_price": sl_price,
                "tp_price": tp_price,
                "leverage": int(suggested_leverage),
                "position_size": position_size,
                "market_mode": market_mode,
                "entry_style": entry_style,
                "grid_levels": grid_levels,
                "grid_spacing_pct": grid_spacing_pct,
                "grid_wait_s": grid_wait_s
            }
        }

    def analyze(self, df: pd.DataFrame, extra_data: Dict[str, Any] = None) -> Dict[str, Any]:
        if df.empty:
            return {"signal": 0, "reason": "No data"}
            
        # 1. Calculate Indicators
        df = self.calculate_indicators(df)
        
        # 2. Market Regime Classification
        classifier = MarketRegimeClassifier()
        regime = classifier.classify(df)
        
        # Pass regime to get_signal via extra_data
        if extra_data is None:
            extra_data = {}
        extra_data['market_regime'] = regime
        
        # 3. Get Signal from last row
        if len(df) < 2:
             return {"signal": 0, "reason": "Not enough data"}
             
        return self.get_signal(df.iloc[-1], df.iloc[-2], extra_data)
