import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def get_data_fallback():
    """
    当境外 Yahoo Finance 直连受限时，提供基于历史走势基线与典型分位数的数据模拟/备用计算，
    确保原型展示与算法逻辑能稳定运转。
    """
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=750, freq='B')
    
    # 模拟近3年符合真实宏观特性的价格序列
    # 黄金牛市：从180点涨到240点附近
    trend_gld = np.linspace(170, 245, len(dates)) + np.cumsum(np.random.normal(0.05, 1.2, len(dates)))
    # 白银：弹性更大
    trend_slv = np.linspace(20, 28, len(dates)) + np.cumsum(np.random.normal(0.02, 0.5, len(dates)))
    # 标普500：高位震荡
    trend_spy = np.linspace(400, 580, len(dates)) + np.cumsum(np.random.normal(0.1, 3.0, len(dates)))
    # TIPS：利率高位承压
    trend_tip = np.linspace(110, 107, len(dates)) + np.cumsum(np.random.normal(-0.01, 0.4, len(dates)))
    # 铜：周期震荡
    trend_cper = np.linspace(22, 27, len(dates)) + np.cumsum(np.random.normal(0.01, 0.3, len(dates)))
    
    df = pd.DataFrame({
        'GLD': trend_gld,
        'SLV': trend_slv,
        'SPY': trend_spy,
        'TIP': trend_tip,
        'CPER': trend_cper
    }, index=dates)
    return df

def run_radar():
    print("⏳ 尝试拉取实时跨市场数据...")
    df = None
    try:
        import yfinance as yf
        tickers = ['GLD', 'SLV', 'CPER', 'SPY', 'TIP']
        raw = yf.download(tickers, period="3y", interval="1d", auto_adjust=True, timeout=10)
        if not raw.empty and 'Close' in raw:
            df = raw['Close'].dropna()
            print("✅ 成功拉取 Yahoo Finance 真实行情数据！")
    except Exception as e:
        print(f"⚠️ Yahoo Finance 接口连接超时 ({e})，自动切换至安全备用基线数据源。")
        
    if df is None or df.empty or len(df) < 50:
        print("💡 启用离线宏观特征模拟序列以验证算法逻辑...")
        df = get_data_fallback()

    gld = df['GLD']
    slv = df['SLV']
    cper = df['CPER']
    spy = df['SPY']
    tip = df['TIP']

    # 1. 核心联动比率
    gold_silver = gld / slv
    spy_gold = spy / gld
    gold_copper = gld / cper

    ratios = {
        "金银比 (Gold/Silver Ratio)": (gold_silver, "贵金属内部投机与轮动情绪"),
        "标普/黄金比 (S&P 500 / Gold)": (spy_gold, "硬资产计价的美股真实估值"),
        "金铜比 (Gold/Copper Ratio)": (gold_copper, "经济衰退预期 vs 制造业复苏")
    }

    print("\n" + "="*70)
    print("📊 宏观资产联动雷达 (Macro Intermarket Radar) - 诊断快照")
    print(f"数据采样截至: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (共 {len(df)} 交易日)")
    print("="*70 + "\n")

    table_data = []

    for name, (series, desc) in ratios.items():
        curr_val = series.iloc[-1]
        val_30d = series.iloc[-22]
        chg_30d = ((curr_val - val_30d) / val_30d) * 100
        pct_rank = (series < curr_val).mean() * 100

        if pct_rank >= 85:
            alert = "🔴 [极度偏高/超买] 处于历史前15%极值"
        elif pct_rank <= 15:
            alert = "🟢 [极度偏低/超卖] 处于历史后15%极值"
        elif pct_rank >= 65:
            alert = "🟡 偏高区间"
        elif pct_rank <= 35:
            alert = "🔵 偏低区间"
        else:
            alert = "⚪ 中性健康"

        table_data.append({
            "指标名称": name,
            "当前比值": f"{curr_val:.2f}",
            "近30天变动": f"{chg_30d:+.2f}%",
            "3年历史分位": f"{pct_rank:.1f}%",
            "状态与预警": alert
        })

    res_df = pd.DataFrame(table_data)
    print(res_df.to_string(index=False))

    # 2. 深度跨资产背离诊断 (黄金 vs 实际利率 TIPS)
    gld_ret_30 = ((gld.iloc[-1] - gld.iloc[-22]) / gld.iloc[-22]) * 100
    tip_ret_30 = ((tip.iloc[-1] - tip.iloc[-22]) / tip.iloc[-22]) * 100

    print("\n" + "-"*70)
    print("🔎 【核心背离专项诊断】黄金 (GLD) 与 实际利率锚 (TIP)：")
    print(f"• 黄金 (GLD) 近 30 天变化率: {gld_ret_30:+.2f}%")
    print(f"• TIPS (TIP，实际利率反向代理) 近 30 天变化率: {tip_ret_30:+.2f}%")

    if gld_ret_30 > 1.0 and tip_ret_30 < -1.0:
        print("🚨 【强烈异常背离警报】")
        print("  -> 现象：美债实际利率居高不下/攀升，但黄金完全脱离利率负相关羁绊逆市上涨！")
        print("  -> 宏观结论：典型的【非美央行储备多元化 + 信用对冲定价】模式，表明资金对主权债务信用存在深层顾虑。")
        print("  -> 仓位启示：维持黄金底仓抗风险；对纯估值驱动型的高估值美股保持警惕。")
    elif gld_ret_30 < -1.0 and tip_ret_30 > 1.0:
        print("⚠️ 【资产定价收缩】黄金随无风险资产吸引力上升而受压制。")
    else:
        print("✅ 【基准联动正常】黄金与真实利率走势相关性符合传统宏观模型。")

    print("="*70 + "\n")

if __name__ == "__main__":
    run_radar()
