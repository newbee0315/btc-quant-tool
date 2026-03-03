import datetime
from typing import Dict, Any, Optional
import logging
import os
import random
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class SocialMediaGenerator:
    # 随机文案模板库 - 强调“自动化回本”主题
    OPENING_TEMPLATES = [
        "🤖 **自动回本挑战 Day {day_n}** | 莫得感情的赚钱机器正在运行...",
        "💥 **回本进度更新！** 量化策略今日战况速报...",
        "📈 **躺平回本系列**：Day {day_n}，机器帮我打工的第 {day_n} 天...",
        "🧬 **人机大战**：相信代码与概率，自动回本挑战第 {day_n} 天！",
        "🚀 **量化实盘日记**：Day {day_n}，目标$13,500，进度条加载中...",
        "⚡ **回本加速中？** Day {day_n} 自动交易数据大公开！",
        "🧠 **摆脱人性弱点**，Day {day_n} 全自动量化回本之路...",
        "🔥 **全自动印钞机启动？** Day {day_n} 实盘数据直接看！",
        "💎 **钻石手还是纸手？** 量化机器人 Day {day_n} 操作大赏",
        "👀 **家人们谁懂啊！** 机器人 Day {day_n} 竟然做出了这种操作...",
        "🎢 **过山车行情？** 量化策略 Day {day_n} 稳如老狗实录",
        "💰 **睡后收入达成？** Day {day_n} 自动交易战绩汇报",
        "🛠️ **打工人vs机器人**：Day {day_n}，到底谁赚得更多？",
        "📉 **抄底还是逃顶？** Day {day_n} 量化模型信号解密",
        "🌊 **冲浪实录**：Day {day_n} 在K线波涛中自动冲浪",
        "🎯 **回本倒计时！** Day {day_n} 距离上岸还有多远？",
        "🩸 **回血进行时**：Day {day_n} 机器人能否带我翻身？",
        "🧘 **佛系持币**：Day {day_n} 一切交给算法，拒绝FOMO",
        "🤖 **算法的胜利？** Day {day_n} 感受数学的暴力美学",
        "📊 **数据不说谎**：Day {day_n} 真实交易记录直接上图",
    ]

    CLOSING_TEMPLATES = [
        "💡 **量化心得:** 市场永远是对的，错的只有我们的偏见。交给代码，严格执行。",
        "💡 **机器日志:** 24小时不间断监控，只为捕捉那一瞬间的确定性。",
        "💡 **今日感悟:** 交易不是预测，而是对可能性的应对。量化就是把应对标准化。",
        "💡 **系统状态:** 策略因子持续扫描中，风控模块随时待命。",
        "💡 **回本哲学:** 慢就是快，稳健复利才是王道。保持耐心，静待花开。",
        "💡 **交易真理:** 截断亏损，让利润奔跑。机器比人更懂执行。",
        "💡 **深夜反思:** 哪怕只有1%的胜率提升，复利下来也是惊人的。",
        "💡 **算法信仰:** 在不确定的市场中，寻找确定的数学概率。",
        "💡 **心态管理:** 涨跌不惊，看庭前花开花落；去留无意，望天上云卷云舒。",
        "💡 **风控第一:** 活下来，由于机会永远存在，本金才是入场券。",
        "💡 **人机对比:** 即使是最好的交易员也会疲惫，但代码永远不会。",
        "💡 **复利奇迹:** 每天进步一点点，坚持下去就是指数级增长。",
        "💡 **止损艺术:** 承认错误是交易的一部分，快速止损是机器人的本能。",
        "💡 **趋势为王:** 顺势而为，逆势必亡。跟随趋势，做时间的朋友。",
        "💡 **量化优势:** 没有情绪，没有恐惧，只有冷冰冰的执行力。",
    ]

    HASHTAG_POOLS = [
        "#BTC #ETH #量化交易 #回本挑战 #缠论 #Python",
        "#加密货币 #自动交易 #被动收入 #投资理财 #区块链",
        "#Web3 #DeFi #Binance #量化策略 #程序员炒币",
        "#交易心得 #实盘记录 #牛市 #熊市 #定投",
        "#技术分析 #MACD #RSI #K线 #交易系统",
        "#金融科技 #AlgoTrading #Crypto #Bitcoin #Ethereum",
        "#躺平 #搞钱 #副业 #理财 #财务自由",
    ]

    def __init__(self, start_date: str = "2026-02-28", initial_debt: float = 13500.0):
        self.start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        self.initial_debt = initial_debt
        self.target_amount = initial_debt # We want to recover this amount
        self.reports_dir = os.path.join(os.getcwd(), "reports")
        os.makedirs(self.reports_dir, exist_ok=True)

    def _get_font(self, size: int):
        """Try to load a nice font, fallback to default"""
        font_paths = [
            "/System/Library/Fonts/PingFang.ttc", # MacOS
            "/System/Library/Fonts/Helvetica.ttc", # MacOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Linux
            "arial.ttf" # Windows/Generic
        ]
        
        for path in font_paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        
        # Fallback to default (ugly but works)
        return ImageFont.load_default()

    def generate_image(self, status: Dict[str, Any]) -> str:
        """
        Generate a social media card image and return the file path.
        """
        try:
            # 1. Prepare Data
            today = datetime.date.today()
            day_n = (today - self.start_date).days + 1
            
            equity = float(status.get('equity', 0.0))
            if equity == 0:
                equity = float(status.get('total_balance', 0.0))
            
            stats = status.get('stats', {})
            realized_pnl = float(stats.get('total_pnl', 0.0))
            unrealized_pnl = float(status.get('unrealized_pnl', 0.0))
            total_profit = realized_pnl + unrealized_pnl
            
            progress_pct = (total_profit / self.initial_debt) * 100
            remaining = self.initial_debt - total_profit
            win_rate = float(stats.get('win_rate', 0.0))
            
            # 2. Setup Canvas
            width = 800
            height = 1100  # Increased height for better spacing
            bg_color = (25, 25, 35) # Slightly blue-ish dark gray
            text_color = (255, 255, 255)
            accent_color = (240, 185, 11) # Binance Yellow
            secondary_text_color = (180, 180, 190)
            
            img = Image.new('RGB', (width, height), color=bg_color)
            draw = ImageDraw.Draw(img)
            
            # Fonts
            font_title = self._get_font(56)
            font_subtitle = self._get_font(28)
            font_metric_label = self._get_font(24)
            font_metric_val = self._get_font(44)
            font_list = self._get_font(26)
            font_footer = self._get_font(18)
            
            # 3. Draw Header
            # Add padding top
            y_cursor = 60
            title_text = f"🤖 自动回本挑战 Day {day_n}"
            draw.text((40, y_cursor), title_text, font=font_title, fill=accent_color)
            y_cursor += 80
            
            subtitle = f"目标: ${self.initial_debt:,.0f} | 进度: {progress_pct:.2f}%"
            draw.text((40, y_cursor), subtitle, font=font_subtitle, fill=text_color)
            y_cursor += 50
            
            # Progress Bar
            bar_x, bar_w, bar_h = 40, 720, 24
            draw.rectangle([bar_x, y_cursor, bar_x + bar_w, y_cursor + bar_h], fill=(50, 50, 60), outline=None)
            
            # Calculate progress width
            progress_clamped = min(max(progress_pct, 0), 100)
            progress_w = (progress_clamped / 100) * bar_w
            
            if progress_w > 0:
                draw.rectangle([bar_x, y_cursor, bar_x + progress_w, y_cursor + bar_h], fill=accent_color, outline=None)
            y_cursor += 80
            
            # 4. Draw Metrics Grid
            # Grid Layout: 2x2
            # Col 1: Equity, Win Rate
            # Col 2: PnL, Remaining
            
            col1_x = 40
            col2_x = 420
            row1_y = y_cursor
            row2_y = y_cursor + 140
            
            # Equity
            draw.text((col1_x, row1_y), "当前权益 (Equity)", font=font_metric_label, fill=secondary_text_color)
            draw.text((col1_x, row1_y + 40), f"${equity:,.2f}", font=font_metric_val, fill=text_color)
            
            # PnL
            pnl_color = (14, 203, 129) if total_profit >= 0 else (246, 70, 93) # Green/Red
            pnl_sign = "+" if total_profit >= 0 else ""
            draw.text((col2_x, row1_y), "累计盈亏 (PnL)", font=font_metric_label, fill=secondary_text_color)
            draw.text((col2_x, row1_y + 40), f"{pnl_sign}${total_profit:,.2f}", font=font_metric_val, fill=pnl_color)
            
            # Win Rate
            draw.text((col1_x, row2_y), "胜率 (Win Rate)", font=font_metric_label, fill=secondary_text_color)
            draw.text((col1_x, row2_y + 40), f"{win_rate:.1f}%", font=font_metric_val, fill=text_color)
            
            # Remaining
            draw.text((col2_x, row2_y), "距离回本 (Remaining)", font=font_metric_label, fill=secondary_text_color)
            remaining_val = max(remaining, 0)
            draw.text((col2_x, row2_y + 40), f"${remaining_val:,.2f}", font=font_metric_val, fill=text_color)
            
            y_cursor = row2_y + 120
            
            # 5. Draw Positions List
            draw.line([(40, y_cursor), (760, y_cursor)], fill=(60, 60, 70), width=2)
            y_cursor += 40
            
            draw.text((40, y_cursor), "📊 当前持仓 (Current Positions)", font=font_subtitle, fill=text_color)
            y_cursor += 60
            
            positions = status.get('positions', {})
            if positions:
                sorted_pos = sorted(positions.items(), key=lambda x: x[1].get('unrealized_pnl', 0), reverse=True)
                for i, (sym, pos) in enumerate(sorted_pos[:6]): # Show top 6
                    clean_sym = sym.replace(':USDT', '')
                    # Translate Side: Long->多, Short->空
                    raw_side = pos.get('side', 'long')
                    side = "多" if raw_side == 'long' else "空"
                    side_color = (14, 203, 129) if raw_side == 'long' else (246, 70, 93)
                    
                    pnl = pos.get('unrealized_pnl', 0.0)
                    roi = pos.get('pnl_pct', 0.0)
                    lev = pos.get('leverage', 1)
                    
                    pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
                    roi_str = f"({roi:+.2f}%)"
                    
                    # Row Layout - Fixed Column Widths to avoid overlap
                    # Col 1: Symbol (x=40)
                    # Col 2: Lev (x=240)
                    # Col 3: Side (x=320)
                    # Col 4: PnL (x=440)
                    # Col 5: ROI (x=600)
                    
                    # 1. Symbol
                    draw.text((40, y_cursor), clean_sym, font=font_list, fill=text_color)
                    
                    # 2. Leverage
                    draw.text((240, y_cursor), f"{lev}x", font=font_list, fill=secondary_text_color)
                    
                    # 3. Side
                    draw.text((320, y_cursor), side, font=font_list, fill=side_color)
                    
                    # 4. PnL
                    pnl_color_pos = (14, 203, 129) if pnl >= 0 else (246, 70, 93)
                    draw.text((440, y_cursor), pnl_str, font=font_list, fill=pnl_color_pos)
                    
                    # 5. ROI
                    draw.text((600, y_cursor), roi_str, font=font_list, fill=secondary_text_color)
                    
                    y_cursor += 60 # Spacing
            else:
                draw.text((40, y_cursor), "当前空仓等待机会 (No Active Positions)", font=font_list, fill=secondary_text_color)
            
            # Footer
            footer_text = f"Generated by 缠论信徒的量化之旅 • {today.strftime('%Y-%m-%d')}"
            
            # Calculate footer position to be at bottom
            footer_w = draw.textlength(footer_text, font=font_footer)
            footer_x = (width - footer_w) / 2
            footer_y = height - 60
            
            draw.text((footer_x, footer_y), footer_text, font=font_footer, fill=(120, 120, 130))
            
            # Save
            filename = f"social_card_{today.strftime('%Y%m%d')}.png"
            filepath = os.path.join(self.reports_dir, filename)
            img.save(filepath)
            logger.info(f"Social card generated: {filepath}")
            
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            return None

    def generate_report(self, status: Dict[str, Any]) -> str:
        """
        Generate a social media ready report string (Markdown for Feishu)
        """
        try:
            # 1. Calculate Time & Progress
            today = datetime.date.today()
            day_n = (today - self.start_date).days + 1
            
            equity = float(status.get('equity', 0.0))
            if equity == 0:
                equity = float(status.get('total_balance', 0.0))
            
            stats = status.get('stats', {})
            realized_pnl = float(stats.get('total_pnl', 0.0))
            unrealized_pnl = float(status.get('unrealized_pnl', 0.0))
            total_profit = realized_pnl + unrealized_pnl
            
            progress_pct = (total_profit / self.initial_debt) * 100
            remaining = self.initial_debt - total_profit
            
            win_rate = float(stats.get('win_rate', 0.0))
            total_trades = int(stats.get('total_trades', 0))
            
            # 2. Catchy Opening & Sentiment
            # Using random template to keep it fresh
            pnl_emoji = "🔥" if total_profit >= 0 else "🩸"
            
            # Select random opening based on templates
            title_template = random.choice(self.OPENING_TEMPLATES)
            title = title_template.format(day_n=day_n)
            
            # Sentiment based on PnL
            if total_profit > 500:
                sentiment = "💥 **炸裂！今日收益再创新高，量化机器杀疯了！**"
            elif total_profit > 100:
                sentiment = "🚀 **起飞！今日收米舒服了，给机器人加鸡腿！**"
            elif total_profit > 0:
                sentiment = "📈 **稳扎稳打！蚊子腿也是肉，回本之路越来越近！**"
            elif total_profit > -100:
                sentiment = "🛡️ **震荡洗盘也不怕，策略防守稳如老狗！**"
            elif total_profit > -300:
                sentiment = "😬 **小亏当赚！市场波动有点大，机器正在抗压...**"
            else:
                sentiment = "⚠️ **回撤预警！机器正在严控风险，等待反击时刻！**"

            # 3. Format Content (Markdown)
            content = f"{sentiment}\n\n"
            content += f"📅 {title}\n"
            content += f"🎯 目标: ${self.initial_debt:,.0f} | 🚀 进度: {progress_pct:.2f}%\n"
            content += "--------------------------------\n"
            
            content += f"{pnl_emoji} **累计盈亏: ${total_profit:+.2f}**\n"
            content += f"💰 **当前权益: ${equity:,.2f}**\n"
            content += f"⏳ **距离回本: ${max(remaining, 0):,.2f}**\n"
            content += f"📊 **胜率: {win_rate:.1f}%** (共 {total_trades} 单)\n"
            content += "--------------------------------\n"
            
            # Positions
            positions = status.get('positions', {})
            if positions:
                content += "**📊 当前持仓:**\n"
                sorted_pos = sorted(positions.items(), key=lambda x: x[1].get('unrealized_pnl', 0), reverse=True)
                for i, (sym, pos) in enumerate(sorted_pos[:5]):
                    clean_sym = sym.replace(':USDT', '')
                    side = "多" if pos.get('side') == 'long' else "空"
                    pnl = pos.get('unrealized_pnl', 0.0)
                    roi = pos.get('pnl_pct', 0.0)
                    lev = pos.get('leverage', 1)
                    pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
                    
                    # Emoji for ROI
                    roi_emoji = "🟢" if roi >= 0 else "🔴"
                    content += f"{roi_emoji} {clean_sym} {side}{lev}x: {pnl_str}U ({roi:.2f}%)\n"
                    
                if len(positions) > 5:
                    content += f"... 等共 {len(positions)} 个持仓\n"
            else:
                content += "🧘 **当前空仓**，量化程序正在扫描最佳入场点...\n"
            
            content += "--------------------------------\n"

            # Closing & Hashtags
            closing_template = random.choice(self.CLOSING_TEMPLATES)
            content += f"{closing_template}\n\n"
            
            hashtags = random.choice(self.HASHTAG_POOLS)
            content += f"{hashtags}"

            return content

        except Exception as e:
            logger.error(f"Failed to generate social report: {e}")
            return "Report Generation Failed"
