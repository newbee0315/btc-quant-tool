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
        """分析中枢 (基于笔重叠)"""
        if len(czsc_obj.bi_list) < 3:
            return {'has_zs': False}
        
        # 取最近三笔
        bi_1 = czsc_obj.bi_list[-3]
        bi_2 = czsc_obj.bi_list[-2]
        bi_3 = czsc_obj.bi_list[-1]
        
        # 确定中枢区间 (High of Lows, Low of Highs)
        # 中枢高点 (ZG) = min(High of Bi1, High of Bi2, High of Bi3) ?? 
        # 标准定义: 中枢区间 = [max(d1, d2, d3), min(g1, g2, g3)]
        # 其中 d=低点, g=高点
        # 但笔的方向交替，如 上-下-上
        # Bi1(上): Low->High, Bi2(下): High->Low, Bi3(上): Low->High
        # 重叠区间 = [max(Bi1.low, Bi2.low, Bi3.low), min(Bi1.high, Bi2.high, Bi3.high)]
        
        d_max = max(bi_1.low, bi_2.low, bi_3.low)
        g_min = min(bi_1.high, bi_2.high, bi_3.high)
        
        if g_min > d_max: # 存在重叠
            range_pct = (g_min - d_max) / d_max * 100
            return {
                'has_zs': True,
                'zg': g_min,
                'zd': d_max,
                'gg': max(bi_1.high, bi_2.high, bi_3.high),
                'dd': min(bi_1.low, bi_2.low, bi_3.low),
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

    def _generate_signals(self, czsc_obj: CZSC) -> Dict[str, bool]:
        """
        生成详细的买卖点信号字典
        
        Args:
            czsc_obj: CZSC对象
            
        Returns:
            Dict[str, bool]: 包含各类买卖点状态的字典
        """
        return {
            # 买点信号
            'buy_1': self._check_first_buy_point(czsc_obj),
            'buy_2': self._check_second_buy_point(czsc_obj),
            'buy_3': self._check_third_buy_point(czsc_obj),
            
            # 卖点信号
            'sell_1': self._check_first_sell_point(czsc_obj),
            'sell_2': self._check_second_sell_point(czsc_obj),
            'sell_3': self._check_third_sell_point(czsc_obj),
            
            # 趋势信号
            'uptrend': czsc_obj.bi_list[-1].direction == 1 if czsc_obj.bi_list else False,
            'downtrend': czsc_obj.bi_list[-1].direction == -1 if czsc_obj.bi_list else False
        }

    def _analyze_divergence(self, czsc_obj: CZSC) -> Dict[str, Any]:
        """分析背驰 (基于笔力度比较)"""
        divergence = {'has_divergence': False, 'type': None, 'strength': 0, 'details': {}}
        
        if len(czsc_obj.bi_list) < 3:
            return divergence

        # 获取当前笔和前一同向笔
        curr_bi = czsc_obj.bi_list[-1]
        prev_bi = czsc_obj.bi_list[-3] # 隔一笔是同向
        
        # 确保方向一致
        if curr_bi.direction != prev_bi.direction:
            return divergence
            
        # 计算力度 (价格幅度)
        curr_amp = abs(curr_bi.high - curr_bi.low)
        prev_amp = abs(prev_bi.high - prev_bi.low)
        
        # 顶背驰判断 (上涨趋势中)
        if curr_bi.direction == 1: # 向上笔
            # 创新高 且 力度减弱
            if curr_bi.high > prev_bi.high and curr_amp < prev_amp:
                divergence.update({'has_divergence': True, 'type': '顶背驰', 'strength': 0.8})
        
        # 底背驰判断 (下跌趋势中)
        elif curr_bi.direction == -1: # 向下笔
            # 创新低 且 力度减弱
            if curr_bi.low < prev_bi.low and curr_amp < prev_amp:
                divergence.update({'has_divergence': True, 'type': '底背驰', 'strength': 0.8})
                
        return divergence

    def _check_first_buy_point(self, czsc_obj: CZSC) -> bool:
        """检查第一类买点 (底背驰)"""
        div = self._analyze_divergence(czsc_obj)
        return div['has_divergence'] and div['type'] == '底背驰'
    
    def _check_first_sell_point(self, czsc_obj: CZSC) -> bool:
        """检查第一类卖点 (顶背驰)"""
        div = self._analyze_divergence(czsc_obj)
        return div['has_divergence'] and div['type'] == '顶背驰'
    
    def _check_second_buy_point(self, czsc_obj: CZSC) -> bool:
        """检查第二类买点 (次级别回调不创新低)"""
        # 需要至少5笔: 下-上(一买)-下(二买)
        if len(czsc_obj.bi_list) < 5:
            return False
            
        bi_1 = czsc_obj.bi_list[-1] # 当前向下笔
        bi_3 = czsc_obj.bi_list[-3] # 前一个向下笔 (一买前的下跌)
        bi_2 = czsc_obj.bi_list[-2] # 中间的向上笔 (一买后的反弹)
        
        # 必须是向下笔结束
        if bi_1.direction != -1:
            return False
            
        # 逻辑:
        # 1. bi_3 是下跌趋势的最后一笔 (底背驰) -> 实际上这里简化判断，只要不创新低
        # 2. bi_1 的低点 > bi_3 的低点 (不创新低)
        # 3. bi_1 的力度 < bi_3 的力度 (衰竭) - 可选
        
        if bi_1.low > bi_3.low:
             # 简单的二买: 回调不创新低
             return True
             
        return False
    
    def _check_second_sell_point(self, czsc_obj: CZSC) -> bool:
        """检查第二类卖点 (次级别反弹不创新高)"""
        if len(czsc_obj.bi_list) < 5:
            return False
            
        bi_1 = czsc_obj.bi_list[-1] # 当前向上笔
        bi_3 = czsc_obj.bi_list[-3] # 前一个向上笔
        
        # 必须是向上笔结束
        if bi_1.direction != 1:
            return False
            
        if bi_1.high < bi_3.high:
            return True
            
        return False
    
    def _check_third_buy_point(self, czsc_obj: CZSC) -> bool:
        """检查第三类买点 (突破中枢后回踩不进中枢)"""
        # 至少需要5笔: ZS(3笔) + 离开笔(1笔) + 回踩笔(1笔)
        if len(czsc_obj.bi_list) < 5:
            return False
            
        bi_last = czsc_obj.bi_list[-1]      # 当前笔 (回踩笔, 应该向下)
        bi_breakout = czsc_obj.bi_list[-2]  # 离开笔 (突破笔, 应该向上)
        
        # 1. 必须是向下笔回踩
        if bi_last.direction != -1:
            return False
            
        # 2. 前一笔必须是向上突破
        if bi_breakout.direction != 1:
            return False
            
        # 3. 分析之前的3笔是否构成中枢
        # 使用 bi_list[-5], [-4], [-3]
        bi_1 = czsc_obj.bi_list[-5]
        bi_2 = czsc_obj.bi_list[-4]
        bi_3 = czsc_obj.bi_list[-3]
        
        d_max = max(bi_1.low, bi_2.low, bi_3.low)
        g_min = min(bi_1.high, bi_2.high, bi_3.high)
        
        has_zs = g_min > d_max
        
        if not has_zs:
            return False
            
        zg = g_min # 中枢高点
        
        # 4. 离开笔必须突破中枢高点 (ZG)
        if bi_breakout.high <= zg:
            return False
            
        # 5. 回踩笔最低点必须高于中枢高点 (ZG) -> 不进中枢
        if bi_last.low > zg:
            return True
            
        return False
    
    def _check_third_sell_point(self, czsc_obj: CZSC) -> bool:
        """检查第三类卖点 (跌破中枢后回抽不进中枢)"""
        if len(czsc_obj.bi_list) < 5:
            return False
            
        bi_last = czsc_obj.bi_list[-1]      # 当前笔 (回抽笔, 应该向上)
        bi_breakdown = czsc_obj.bi_list[-2] # 离开笔 (跌破笔, 应该向下)
        
        # 1. 必须是向上笔回抽
        if bi_last.direction != 1:
            return False
            
        # 2. 前一笔必须是向下跌破
        if bi_breakdown.direction != -1:
            return False
            
        # 3. 分析之前的3笔是否构成中枢
        bi_1 = czsc_obj.bi_list[-5]
        bi_2 = czsc_obj.bi_list[-4]
        bi_3 = czsc_obj.bi_list[-3]
        
        d_max = max(bi_1.low, bi_2.low, bi_3.low)
        g_min = min(bi_1.high, bi_2.high, bi_3.high)
        
        has_zs = g_min > d_max
        
        if not has_zs:
            return False
            
        zd = d_max # 中枢低点
        
        # 4. 离开笔必须跌破中枢低点 (ZD)
        if bi_breakdown.low >= zd:
            return False
            
        # 5. 回抽笔最高点必须低于中枢低点 (ZD) -> 不进中枢
        if bi_last.high < zd:
            return True
            
        return False
    
    def _get_trend_signal(self, czsc_obj: CZSC) -> int:
        """获取趋势信号"""
        # 简单的趋势判断: 顶底分型不断抬高为多头(1)，降低为空头(-1)
        if len(czsc_obj.bi_list) < 4:
            return 0
            
        last_bi = czsc_obj.bi_list[-1]
        prev_bi = czsc_obj.bi_list[-3]
        
        if last_bi.high > prev_bi.high and last_bi.low > prev_bi.low:
            return 1
        elif last_bi.high < prev_bi.high and last_bi.low < prev_bi.low:
            return -1
            
        return 0

    def _get_momentum_signal(self, czsc_obj: CZSC) -> int:
        """获取动量信号 (基于笔力度)"""
        div = self._analyze_divergence(czsc_obj)
        if div['has_divergence']:
            if div['type'] == '底背驰':
                return 1 # 动量反转向上
            elif div['type'] == '顶背驰':
                return -1 # 动量反转向下
        return 0
    
    def _get_pattern_signal(self, czsc_obj: CZSC) -> int:
        """获取模式信号 (基于买卖点)"""
        tp = self._analyze_trade_points(czsc_obj)
        
        score = 0
        if tp.get('first_buy') or tp.get('second_buy') or tp.get('third_buy'):
            score += 1
        if tp.get('first_sell') or tp.get('second_sell') or tp.get('third_sell'):
            score -= 1
            
        return score
    
    def _get_composite_signal(self, signals: Dict[str, Any]) -> int:
        """获取综合信号"""
        # 简单加权
        score = signals.get('trend', 0) + signals.get('momentum', 0) + signals.get('pattern', 0)
        
        if score > 1: return 1
        if score < -1: return -1
        return 0
    
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