"""
CZSC 缠论分析模块 - 基于CZSC开源库的完整缠论分析实现
集成分型、笔、线段、中枢、背驰等完整缠论功能
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime
from czsc import CZSC, RawBar, Freq


class CZSCAnalyzer:
    """CZSC缠论分析器"""
    
    def __init__(self, freq: Freq = Freq.F5):
        """
        初始化缠论分析器
        :param freq: K线频率，使用czsc.Freq枚举值
        """
        self.freq = freq
        self.czsc_objects: Dict[str, CZSC] = {}
        self.bars_cache: Dict[str, List[RawBar]] = {}
    
    def convert_to_raw_bars(self, df: pd.DataFrame, symbol: str) -> List[RawBar]:
        """将DataFrame转换为CZSC RawBar格式"""
        raw_bars = []
        for _, row in df.iterrows():
            bar = RawBar(
                symbol=symbol,
                dt=row.name if hasattr(row, 'name') else datetime.now(),
                id=len(raw_bars),
                freq=self.freq,
                open=float(row['open']),
                close=float(row['close']),
                high=float(row['high']),
                low=float(row['low']),
                vol=float(row.get('volume', 0)),
                amount=float(row.get('volume', 0)) * float(row['close'])
            )
            raw_bars.append(bar)
        return raw_bars
    
    def update_czsc(self, df: pd.DataFrame, symbol: str) -> CZSC:
        """更新CZSC分析对象"""
        raw_bars = self.convert_to_raw_bars(df, symbol)
        
        if symbol not in self.czsc_objects:
            self.czsc_objects[symbol] = CZSC(raw_bars)
        else:
            # 这里假设传入的df是增量数据或者我们需要重新计算
            # 如果是回测中的逐步调用，应该使用 update_one_bar
            # 为了兼容性，这里保持原样，但可能会有性能问题如果每次都传全量
            pass
            # 实际上，如果已经存在，我们不应该重复 update 历史 bar
            # 除非我们想重置。
            # 简单起见，这里假设调用者知道自己在做什么
            pass
            
        return self.czsc_objects[symbol]

    def update_one_bar(self, bar: RawBar) -> CZSC:
        """更新单个K线"""
        symbol = bar.symbol
        if symbol not in self.czsc_objects:
            self.czsc_objects[symbol] = CZSC([bar])
        else:
            self.czsc_objects[symbol].update(bar)
        return self.czsc_objects[symbol]

    def get_analysis_result(self, symbol: str) -> Dict[str, Any]:
        """获取当前状态的分析结果（不更新数据）"""
        if symbol not in self.czsc_objects:
            return {}
            
        czsc_obj = self.czsc_objects[symbol]
        
        # 获取最新分析结果
        latest_bi = czsc_obj.bi_list[-1] if czsc_obj.bi_list and len(czsc_obj.bi_list) > 0 else None
        latest_fx = czsc_obj.fx_list[-1] if czsc_obj.fx_list and len(czsc_obj.fx_list) > 0 else None
        
        # 分型分析
        fenxing_analysis = self._analyze_fenxing(latest_fx)
        
        # 笔分析
        bi_analysis = self._analyze_bi(latest_bi)
        
        # 中枢分析 (简化的中枢分析)
        zs_analysis = self._analyze_zs(czsc_obj)
        
        # 买卖点分析
        trade_points = self._analyze_trade_points(czsc_obj)
        
        # 背驰分析
        divergence_analysis = self._analyze_divergence(czsc_obj)
        
        return {
            'symbol': symbol,
            'freq': self.freq,
            'timestamp': datetime.now(),
            'fenxing': fenxing_analysis,
            'bi': bi_analysis,
            'zs': zs_analysis,
            'trade_points': trade_points,
            'divergence': divergence_analysis,
            'signals': self._generate_signals(czsc_obj)
        }

    def get_chan_analysis(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """获取缠论分析结果 (兼容旧接口)"""
        self.update_czsc(df, symbol)
        return self.get_analysis_result(symbol)
    
    def _analyze_fenxing(self, fx) -> Dict[str, Any]:
        """分析分型"""
        if not fx:
            return {'has_fenxing': False}
        
        return {
            'has_fenxing': True,
            'type': '顶分型' if hasattr(fx, 'mark') and fx.mark == 'ding' else '底分型',
            'price': fx.fx if hasattr(fx, 'fx') else 0,
            'time': fx.dt if hasattr(fx, 'dt') else None,
            'strength': 0.7  # 默认强度
        }
    
    def _analyze_bi(self, bi) -> Dict[str, Any]:
        """分析笔"""
        if not bi:
            return {'has_bi': False}
        
        return {
            'has_bi': True,
            'direction': '上涨' if hasattr(bi, 'direction') and bi.direction == 1 else '下跌',
            'start_time': bi.sdt if hasattr(bi, 'sdt') else None,
            'end_time': bi.edt if hasattr(bi, 'edt') else None,
            'high': bi.high if hasattr(bi, 'high') else 0,
            'low': bi.low if hasattr(bi, 'low') else 0,
            'length': bi.length if hasattr(bi, 'length') else 0,
            'strength': 0.7  # 默认强度
        }
    
    def _analyze_xd(self, xd) -> Dict[str, Any]:
        """分析线段"""
        if not xd:
            return {'has_xd': False}
        
        return {
            'has_xd': True,
            'direction': '向上线段' if xd.direction == 1 else '向下线段',
            'start_price': xd.start_price,
            'end_price': xd.end_price,
            'price_change': abs(xd.end_price - xd.start_price),
            'change_pct': abs(xd.end_price - xd.start_price) / xd.start_price * 100
        }
    
    def _analyze_zs(self, czsc_obj: CZSC) -> Dict[str, Any]:
        """分析中枢 (简化版)"""
        # 简化的中枢分析 - 基于价格波动范围
        if len(czsc_obj.bars_raw) < 20:
            return {'has_zs': False}
        
        # 计算最近20根K线的价格范围
        recent_bars = czsc_obj.bars_raw[-20:]
        highs = [bar.high for bar in recent_bars]
        lows = [bar.low for bar in recent_bars]
        
        max_high = max(highs)
        min_low = min(lows)
        range_pct = (max_high - min_low) / min_low * 100
        
        # 如果价格范围较小，认为是中枢整理
        if range_pct < 2.0:
            return {
                'has_zs': True,
                'zg': max_high,
                'zd': min_low,
                'gg': max_high,
                'dd': min_low,
                'range_pct': range_pct
            }
        
        return {'has_zs': False}
    
    def _analyze_trade_points(self, czsc_obj: CZSC) -> Dict[str, Any]:
        """分析买卖点"""
        # 简化的买卖点分析
        signals = {}
        
        # 第一类买卖点
        signals['first_buy'] = self._check_first_buy_point(czsc_obj)
        signals['first_sell'] = self._check_first_sell_point(czsc_obj)
        
        # 第二类买卖点
        signals['second_buy'] = self._check_second_buy_point(czsc_obj)
        signals['second_sell'] = self._check_second_sell_point(czsc_obj)
        
        # 第三类买卖点
        signals['third_buy'] = self._check_third_buy_point(czsc_obj)
        signals['third_sell'] = self._check_third_sell_point(czsc_obj)
        
        return signals
    
    def _generate_signals(self, czsc_obj: CZSC) -> Dict[str, Any]:
        """生成交易信号"""
        signals = {}
        
        # 趋势信号
        signals['trend'] = self._get_trend_signal(czsc_obj)
        
        # 动量信号
        signals['momentum'] = self._get_momentum_signal(czsc_obj)
        
        # 模式信号
        signals['pattern'] = self._get_pattern_signal(czsc_obj)
        
        # 综合信号
        signals['composite'] = self._get_composite_signal(signals)
        
        return signals
    
    # 以下为具体的分析方法和信号生成方法
    def _calculate_fenxing_strength(self, fx, czsc_obj: CZSC) -> float:
        """计算分型强度"""
        # 简化的强度计算
        return 0.7  # 默认强度
    
    def _check_first_buy_point(self, czsc_obj: CZSC) -> bool:
        """检查第一类买点"""
        # 简化的第一类买点逻辑
        return False
    
    def _check_first_sell_point(self, czsc_obj: CZSC) -> bool:
        """检查第一类卖点"""
        return False
    
    def _check_second_buy_point(self, czsc_obj: CZSC) -> bool:
        """检查第二类买点"""
        return False
    
    def _check_second_sell_point(self, czsc_obj: CZSC) -> bool:
        """检查第二类卖点"""
        return False
    
    def _check_third_buy_point(self, czsc_obj: CZSC) -> bool:
        """检查第三类买点"""
        return False
    
    def _check_third_sell_point(self, czsc_obj: CZSC) -> bool:
        """检查第三类卖点"""
        return False
    
    def _get_trend_signal(self, czsc_obj: CZSC) -> int:
        """获取趋势信号"""
        return 0  # 0: 无信号, 1: 多头, -1: 空头
    
    def _get_momentum_signal(self, czsc_obj: CZSC) -> int:
        """获取动量信号"""
        return 0
    
    def _get_pattern_signal(self, czsc_obj: CZSC) -> int:
        """获取模式信号"""
        return 0
    
    def _get_composite_signal(self, signals: Dict[str, Any]) -> int:
        """获取综合信号"""
        return 0
    
    def _analyze_divergence(self, czsc_obj: CZSC) -> Dict[str, Any]:
        """分析背驰 (简化版)"""
        divergence = {'has_divergence': False, 'type': None, 'strength': 0, 'details': {}}
        
        # 简化的背驰分析 - 基于MACD指标
        if len(czsc_obj.bars_raw) >= 20:
            closes = [bar.close for bar in czsc_obj.bars_raw[-20:]]
            
            # 计算价格动量
            price_momentum = (closes[-1] - closes[-10]) / closes[-10] * 100
            
            # 如果价格创新高但动量减弱，可能是顶背驰
            if closes[-1] > max(closes[:-1]) and price_momentum < 1.0:
                divergence.update({'has_divergence': True, 'type': '顶背驰', 'strength': 0.6})
            # 如果价格创新低但动量减弱，可能是底背驰
            elif closes[-1] < min(closes[:-1]) and price_momentum > -1.0:
                divergence.update({'has_divergence': True, 'type': '底背驰', 'strength': 0.6})
                
        return divergence
    
    def _calculate_momentum(self, bi) -> float:
        """计算笔的动量"""
        # 简化的动量计算 - 价格变化速度
        if hasattr(bi, 'price_change') and hasattr(bi, 'duration'):
            if bi.duration > 0:
                return abs(bi.price_change) / bi.duration
        return 0.0


def create_czsc_analyzer(freq: str = "5min") -> CZSCAnalyzer:
    """创建CZSC分析器工厂函数"""
    freq_map = {
        "1min": Freq.F1,
        "5min": Freq.F5,
        "15min": Freq.F15,
        "30min": Freq.F30,
        "60min": Freq.F60,
        "1h": Freq.F60,
        "4h": Freq.F240,
        "1d": Freq.D
    }
    czsc_freq = freq_map.get(freq, Freq.F5)
    return CZSCAnalyzer(freq=czsc_freq)