import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# 数据源配置（主源 + 交叉验证备源）
# ─────────────────────────────────────────────────────────────
# 主源：直接使用商品期货现货价格（$/盎司 or $/磅）
# GC=F  黄金期货  (美元/盎司)
# SI=F  白银期货  (美元/盎司)
# HG=F  铜期货    (美元/磅)   → 乘以 22.0462 转换为 $/kg 后与金银同比
# SPY   标普500 ETF
# TIP   TIPS ETF (实际利率反向代理)

# 交叉验证源：ETF 价格 + 修正系数（当期货数据不完整时兜底）
# GLD 每份 ≈ 0.0948 盎司黄金 → 金价($/oz) ≈ GLD / 0.0948
# SLV 每份 ≈ 0.9330 盎司白银 → 银价($/oz) ≈ SLV / 0.9330
# 修正系数来自 SPDR/iShares 官方披露，每年略有变化

GLD_OZ_PER_SHARE = 0.0948    # 每份 GLD 对应的黄金盎司数
SLV_OZ_PER_SHARE = 0.9330    # 每份 SLV 对应的白银盎司数

TICKERS_PRIMARY = {
    'GOLD': 'GC=F',
    'SILVER': 'SI=F',
    'COPPER': 'HG=F',
    'SP500': 'SPY',
    'TIPS': 'TIP',
}

TICKERS_BACKUP = {
    'GOLD_ETF': 'GLD',
    'SILVER_ETF': 'SLV',
    'SP500': 'SPY',
    'TIPS': 'TIP',
}

# ─────────────────────────────────────────────────────────────
# 数据拉取与交叉验证
# ─────────────────────────────────────────────────────────────
def fetch_with_cross_validation():
    print("📡 [主源] 拉取商品期货现货数据 (GC=F / SI=F / HG=F)...")
    raw = yf.download(list(TICKERS_PRIMARY.values()), period="3y",
                      interval="1d", auto_adjust=True, timeout=15)
    df_primary = raw['Close'].dropna(how='all') if 'Close' in raw else pd.DataFrame()

    # 检查主源完整性
    has_gold   = 'GC=F' in df_primary.columns and df_primary['GC=F'].notna().sum() > 100
    has_silver = 'SI=F' in df_primary.columns and df_primary['SI=F'].notna().sum() > 100
    has_copper = 'HG=F' in df_primary.columns and df_primary['HG=F'].notna().sum() > 100

    print(f"   黄金期货 (GC=F): {'✅' if has_gold else '❌'} | "
          f"白银期货 (SI=F): {'✅' if has_silver else '❌'} | "
          f"铜期货 (HG=F): {'✅' if has_copper else '❌'}")

    # 拉取交叉验证源（ETF）
    print("📡 [验证源] 拉取 ETF 价格数据 (GLD / SLV) 进行交叉校验...")
    raw_b = yf.download(list(TICKERS_BACKUP.values()), period="3y",
                        interval="1d", auto_adjust=True, timeout=15)
    df_backup = raw_b['Close'].dropna(how='all') if 'Close' in raw_b else pd.DataFrame()

    # 对齐时间索引（取交集日期）
    all_data = {}

    # ── 黄金价格（$/盎司）──
    if has_gold:
        gold = df_primary['GC=F'].dropna()
        source_gold = "GC=F 期货"
    elif 'GLD' in df_backup.columns:
        gold = (df_backup['GLD'] / GLD_OZ_PER_SHARE).dropna()
        source_gold = "GLD ETF 折算"
    else:
        raise ValueError("无法获取黄金数据，请检查网络连接")
    all_data['GOLD'] = gold

    # ── 白银价格（$/盎司）──
    if has_silver:
        silver = df_primary['SI=F'].dropna()
        source_silver = "SI=F 期货"
    elif 'SLV' in df_backup.columns:
        silver = (df_backup['SLV'] / SLV_OZ_PER_SHARE).dropna()
        source_silver = "SLV ETF 折算"
    else:
        raise ValueError("无法获取白银数据，请检查网络连接")
    all_data['SILVER'] = silver

    # ── 铜价（统一换算为 $/盎司 便于与金银同单位比较）──
    # HG=F 单位是 $/磅，1磅 = 14.5833 盎司
    if has_copper:
        copper_lb = df_primary['HG=F'].dropna()
        copper = copper_lb * 14.5833    # 转为 $/盎司
        source_copper = "HG=F 期货"
    else:
        copper = None
        source_copper = "不可用"
    if copper is not None:
        all_data['COPPER'] = copper

    # ── SPY & TIP ──
    for col in ['SPY', 'TIP']:
        if col in df_primary.columns and df_primary[col].notna().sum() > 100:
            all_data[col] = df_primary[col].dropna()
        elif col in df_backup.columns:
            all_data[col] = df_backup[col].dropna()

    df = pd.DataFrame(all_data).dropna(how='any')
    print(f"\n✅ 数据拼装完成：{len(df)} 个交易日（{df.index[0].date()} → {df.index[-1].date()}）")

    # ── 交叉验证检查 ──
    print("\n🔍 [交叉验证] 期货价格 vs ETF 折算价格对比（最新收盘日）：")
    if has_gold and 'GLD' in df_backup.columns:
        gold_etf_derived = df_backup['GLD'].iloc[-1] / GLD_OZ_PER_SHARE
        gold_futures = df_primary['GC=F'].dropna().iloc[-1]
        diff_pct = abs(gold_futures - gold_etf_derived) / gold_etf_derived * 100
        print(f"   黄金：期货 ${gold_futures:.2f}/oz | ETF折算 ${gold_etf_derived:.2f}/oz | 偏差 {diff_pct:.2f}%  "
              f"{'✅ 正常' if diff_pct < 2 else '⚠️ 偏差较大，请检查'}")

    if has_silver and 'SLV' in df_backup.columns:
        silver_etf_derived = df_backup['SLV'].iloc[-1] / SLV_OZ_PER_SHARE
        silver_futures = df_primary['SI=F'].dropna().iloc[-1]
        diff_pct = abs(silver_futures - silver_etf_derived) / silver_etf_derived * 100
        print(f"   白银：期货 ${silver_futures:.2f}/oz | ETF折算 ${silver_etf_derived:.2f}/oz | 偏差 {diff_pct:.2f}%  "
              f"{'✅ 正常' if diff_pct < 2 else '⚠️ 偏差较大，请检查'}")

    return df, {
        'gold': source_gold, 'silver': source_silver,
        'copper': source_copper
    }

# ─────────────────────────────────────────────────────────────
# 比率计算
# ─────────────────────────────────────────────────────────────
def compute_ratios(df):
    ratios = {}
    ratios['gold_silver'] = df['GOLD'] / df['SILVER']          # 金银比（无量纲，真实盎司价格比）
    ratios['spy_gold']    = df['SPY']  / (df['GOLD'] / 10)     # 标普/黄金（用金价/10作基准方便比较）
    if 'COPPER' in df.columns:
        ratios['gold_copper'] = df['GOLD'] / df['COPPER']      # 金铜比（同为$/盎司单位）

    # 实际利率背离（近30日）
    ratios['tip'] = df['TIP']
    ratios['gold_raw'] = df['GOLD']
    return ratios

# ─────────────────────────────────────────────────────────────
# 指标统计函数
# ─────────────────────────────────────────────────────────────
def metric_stats(series, name, desc, expected_range=None):
    s = series.dropna()
    curr = float(s.iloc[-1])
    d30  = float(s.iloc[-22]) if len(s) >= 22 else float(s.iloc[0])
    chg_30 = ((curr - d30) / d30) * 100
    pct_rank = float((s < curr).mean() * 100)

    # 合理性校验
    validation_note = ""
    if expected_range:
        lo, hi = expected_range
        if not (lo <= curr <= hi):
            validation_note = f"⚠️ 当前值 {curr:.1f} 超出预期区间 [{lo}, {hi}]，请核查数据源"

    if pct_rank >= 85:
        status_color, status_text = "rose", "极度高估 (警戒)"
    elif pct_rank <= 15:
        status_color, status_text = "sky", "极度低估 (机会)"
    elif pct_rank >= 65:
        status_color, status_text = "amber", "偏高区间"
    elif pct_rank <= 35:
        status_color, status_text = "indigo", "偏低区间"
    else:
        status_color, status_text = "emerald", "中性合理"

    return {
        "name": name, "desc": desc,
        "current": round(curr, 2),
        "chg_30": round(chg_30, 2),
        "pct_rank": round(pct_rank, 1),
        "status_color": status_color,
        "status_text": status_text,
        "validation_note": validation_note,
        "history": [round(float(v), 2) for v in s.values],
    }

# ─────────────────────────────────────────────────────────────
# HTML 看板生成
# ─────────────────────────────────────────────────────────────
def generate_dashboard(df, ratios, sources):
    dates = [d.strftime('%Y-%m-%d') for d in df.index]

    m1 = metric_stats(
        ratios['gold_silver'], "金银比 (Gold/Silver Ratio)",
        "反映贵金属内部轮动及投机/工业情绪热度。历史正常区间 50–100，>80 白银被低估。",
        expected_range=(40, 120)         # 合理性校验范围
    )
    m2 = metric_stats(
        ratios['spy_gold'],  "标普/黄金比 (S&P 500 / Gold×10)",
        "以硬资产重新度量美股权益的真实购买力估值与泡沫程度。",
        expected_range=(0.3, 3.0)
    )
    m3 = metric_stats(
        ratios['gold_copper'], "金铜比 (Gold/Copper Ratio)",
        "经济衰退避险预期 vs 顺周期制造业复苏晴雨表。金强铜弱=衰退，铜强金弱=复苏。",
        expected_range=(200, 800)
    ) if 'gold_copper' in ratios else None

    gold_ret_30 = round(float(((ratios['gold_raw'].iloc[-1] - ratios['gold_raw'].iloc[-22])
                               / ratios['gold_raw'].iloc[-22]) * 100), 2)
    tip_ret_30  = round(float(((ratios['tip'].iloc[-1] - ratios['tip'].iloc[-22])
                               / ratios['tip'].iloc[-22]) * 100), 2)
    gold_latest = round(float(ratios['gold_raw'].iloc[-1]), 2)

    if gold_ret_30 > 1.0 and tip_ret_30 < -1.0:
        anomaly_title = "🚨 强烈背离：黄金逆实际利率压制上涨"
        anomaly_desc  = "美债实际利率居高，但黄金摆脱贴现率约束强劲上行。典型的去美元化储备买盘信号。"
        anomaly_badge = "bg-rose-500/10 text-rose-400 border-rose-500/20"
    else:
        anomaly_title = "宏观资产定价逻辑基准同步"
        anomaly_desc  = f"黄金近30天 {gold_ret_30:+}%，TIPS近30天 {tip_ret_30:+}%。传导路径顺畅，未出现极端脱钩。"
        anomaly_badge = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"

    def card_html(m, chart_id=None):
        chg_color = "text-emerald-400" if m['chg_30'] >= 0 else "text-rose-400"
        chg_arrow = "↑" if m['chg_30'] >= 0 else "↓"
        warn = f'<p class="mt-2 text-xs text-amber-400">{m["validation_note"]}</p>' if m['validation_note'] else ''
        return f"""
      <div class="p-5 rounded-2xl bg-slate-900 border border-slate-800/80 hover:border-slate-700 transition flex flex-col">
        <div class="flex items-start justify-between gap-2">
          <h4 class="font-bold text-slate-200 text-sm leading-tight">{m['name']}</h4>
          <span class="shrink-0 px-2 py-0.5 rounded text-[11px] font-medium
            bg-{m['status_color']}-500/10 text-{m['status_color']}-400 border border-{m['status_color']}-500/20">
            {m['status_text']}
          </span>
        </div>
        <p class="text-xs text-slate-400 mt-1 leading-relaxed">{m['desc']}</p>
        {warn}
        <div class="mt-4 flex items-baseline gap-3">
          <span class="text-3xl font-extrabold font-mono text-white tracking-tight">{m['current']}</span>
          <span class="text-xs font-mono font-semibold {chg_color}">{chg_arrow} {abs(m['chg_30']):.2f}% (30天)</span>
        </div>
        <div class="mt-5 pt-4 border-t border-slate-800/60">
          <div class="flex justify-between text-xs text-slate-400 mb-1.5 font-mono">
            <span>3年历史分位</span>
            <span class="text-slate-200 font-semibold">{m['pct_rank']}%</span>
          </div>
          <div class="relative w-full bg-slate-800 rounded-full h-2 overflow-visible">
            <div class="bg-gradient-to-r from-indigo-500 to-amber-500 h-2 rounded-full" style="width:{m['pct_rank']}%"></div>
            <div class="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-indigo-400 shadow"
              style="left:calc({m['pct_rank']}% - 6px)"></div>
          </div>
          <div class="flex justify-between text-[10px] text-slate-600 mt-1 font-mono">
            <span>3yr Low</span><span>Median</span><span>3yr High</span>
          </div>
        </div>
      </div>"""

    cards = card_html(m1) + card_html(m2)
    if m3:
        cards += card_html(m3)

    m3_series = json.dumps(m3['history']) if m3 else '[]'
    m3_label  = m3['name'] if m3 else ''

    # 数据源标注
    src_note = f"黄金: {sources['gold']} ｜ 白银: {sources['silver']} ｜ 铜: {sources['copper']}"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MacroRadar | 宏观资产联动雷达</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
  <script>tailwind.config={{darkMode:'class'}}</script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased">

  <header class="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-amber-500 to-indigo-500 flex items-center justify-center font-bold text-white">Ω</div>
        <div>
          <span class="font-bold text-lg tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">MacroRadar</span>
          <span class="text-xs text-slate-500 ml-2 font-mono">v0.2 · 双源交叉验证</span>
        </div>
      </div>
      <div class="flex items-center gap-3 text-xs text-slate-400">
        <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700/60">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>每日自动更新
        </span>
        <span class="hidden sm:inline font-mono text-slate-500">{datetime.now().strftime('%Y-%m-%d %H:%M UTC+8')}</span>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-7">

    <div>
      <h1 class="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">跨市场资产联动与异常预警</h1>
      <p class="text-slate-400 text-sm mt-1">面向美股与贵金属严肃配置者 · 数据源：商品期货现货价格 + ETF 双源交叉验证</p>
    </div>

    <!-- 黄金价格实时锚点 -->
    <div class="inline-flex items-center gap-3 px-4 py-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-sm">
      <span class="text-amber-400 font-semibold">黄金现货</span>
      <span class="text-white font-bold font-mono text-lg">${gold_latest:.2f} <span class="text-xs text-amber-300/70">$/盎司</span></span>
      <span class="text-slate-500 text-xs">(GC=F 期货结算价)</span>
    </div>

    <!-- 背离警报横幅 -->
    <div class="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div class="space-y-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold border {anomaly_badge}">跨资产背离专项</span>
          <h3 class="font-semibold text-slate-200 text-sm">{anomaly_title}</h3>
        </div>
        <p class="text-xs text-slate-400 max-w-3xl leading-relaxed">{anomaly_desc}</p>
      </div>
      <div class="flex gap-3 shrink-0">
        <div class="bg-slate-950/60 px-3.5 py-2 rounded-xl border border-slate-800/80 text-center">
          <div class="text-[11px] text-slate-500">黄金 30D</div>
          <div class="text-sm font-bold font-mono {'text-emerald-400' if gold_ret_30>=0 else 'text-rose-400'}">{gold_ret_30:+.2f}%</div>
        </div>
        <div class="bg-slate-950/60 px-3.5 py-2 rounded-xl border border-slate-800/80 text-center">
          <div class="text-[11px] text-slate-500">TIPS 30D</div>
          <div class="text-sm font-bold font-mono {'text-emerald-400' if tip_ret_30>=0 else 'text-rose-400'}">{tip_ret_30:+.2f}%</div>
        </div>
      </div>
    </div>

    <!-- 核心指标卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-{'2' if not m3 else '3'} gap-5">
      {cards}
    </div>

    <!-- 历史走势图 -->
    <div class="p-6 rounded-2xl bg-slate-900 border border-slate-800/80">
      <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
        <div>
          <h3 class="font-bold text-base text-slate-200">近 3 年宏观联动比率历史走势</h3>
          <p class="text-xs text-slate-500">支持区间缩放（底部滑块）· 十字光标悬停查值 · 图例点击隐藏/显示</p>
        </div>
      </div>
      <div id="chart" class="w-full h-80 sm:h-96 mt-4"></div>
    </div>

    <!-- 数据透明度声明 -->
    <div class="text-xs text-slate-600 font-mono flex flex-wrap gap-x-4 gap-y-1">
      <span>📡 数据源: {src_note}</span>
      <span>🔄 更新时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</span>
      <span>⚠️ 仅供参考，不构成投资建议</span>
    </div>

    <!-- CTA -->
    <div class="p-6 rounded-2xl bg-gradient-to-r from-indigo-950/60 via-slate-900 to-slate-900 border border-indigo-900/40 flex flex-col md:flex-row items-center justify-between gap-5">
      <div class="text-center md:text-left">
        <h4 class="font-bold text-white">想每天盘前收到最新背离警报与宏观归因简报？</h4>
        <p class="text-xs text-slate-400 mt-1">内测阶段，加入早期配置者清单，第一时间获取极端背离推演报告。</p>
      </div>
      <div class="flex w-full md:w-auto gap-2">
        <input type="email" placeholder="输入你的邮箱..." class="bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-full sm:w-56">
        <button class="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-4 py-2 rounded-xl transition shrink-0 shadow-lg shadow-indigo-600/30">立即订阅</button>
      </div>
    </div>
  </main>

  <script>
  const dates = {json.dumps(dates)};
  const chart = echarts.init(document.getElementById('chart'),'dark',{{renderer:'canvas'}});
  chart.setOption({{
    backgroundColor:'transparent',
    tooltip:{{trigger:'axis',backgroundColor:'#0f172a',borderColor:'#334155',
      textStyle:{{color:'#f8fafc',fontSize:12}},
      axisPointer:{{type:'cross',label:{{backgroundColor:'#475569'}}}}}},
    legend:{{data:['金银比','标普/黄金比×10','{m3_label}'],top:0,textStyle:{{color:'#94a3b8',fontSize:12}}}},
    grid:{{left:'2%',right:'2%',bottom:'10%',top:'12%',containLabel:true}},
    dataZoom:[
      {{type:'inside',start:60,end:100}},
      {{type:'slider',bottom:'0%',height:20,borderColor:'#1e293b',fillerColor:'rgba(99,102,241,0.2)'}}
    ],
    xAxis:{{type:'category',data:dates,axisLine:{{lineStyle:{{color:'#334155'}}}},axisLabel:{{color:'#64748b'}}}},
    yAxis:[
      {{type:'value',name:'金银比',position:'left',splitLine:{{lineStyle:{{color:'#1e293b'}}}},axisLabel:{{color:'#64748b'}}}},
      {{type:'value',name:'标普/黄金',position:'right',splitLine:{{show:false}},axisLabel:{{color:'#64748b'}}}}
    ],
    series:[
      {{name:'金银比',type:'line',smooth:true,showSymbol:false,yAxisIndex:0,
        data:{json.dumps(m1['history'])},itemStyle:{{color:'#f59e0b'}},lineStyle:{{width:2}}}},
      {{name:'标普/黄金比×10',type:'line',smooth:true,showSymbol:false,yAxisIndex:1,
        data:{json.dumps(m2['history'])},itemStyle:{{color:'#6366f1'}},lineStyle:{{width:2}}}},
      {{name:'{m3_label}',type:'line',smooth:true,showSymbol:false,yAxisIndex:0,
        data:{m3_series},itemStyle:{{color:'#10b981'}},lineStyle:{{width:1.5,type:'dashed'}}}}
    ]
  }});
  window.addEventListener('resize',()=>chart.resize());
  </script>
</body>
</html>"""

    out = r"C:\Users\lee\.gemini\antigravity\scratch\macro_radar\index.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n🎉 看板已生成：{out}")
    print(f"   金银比: {m1['current']} (3yr分位: {m1['pct_rank']}%) {'✅' if not m1['validation_note'] else '⚠️'}")
    print(f"   {m1['validation_note'] if m1['validation_note'] else ''}")


if __name__ == "__main__":
    df, sources = fetch_with_cross_validation()
    ratios = compute_ratios(df)
    generate_dashboard(df, ratios, sources)
