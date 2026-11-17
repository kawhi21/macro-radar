# MacroRadar 🌐

**宏观资产联动雷达** — 面向美股与贵金属严肃配置者的跨资产异常背离预警看板。

🔗 **Live Demo**: https://macro-radar-five.vercel.app

## 核心指标

| 指标 | 数据源 | 说明 |
|---|---|---|
| 金银比 (Gold/Silver) | GC=F / SI=F 期货 | 贵金属内部轮动情绪，历史正常 50-100 |
| 标普/黄金比 | SPY / GC=F | 以硬资产计价的美股真实估值 |
| 金铜比 (Gold/Copper) | GC=F / HG=F 期货 | 经济衰退 vs 复苏晴雨表 |

## 特性

- ✅ 商品期货现货价格（非 ETF 价格）
- ✅ 双源交叉验证（期货 + ETF 折算）
- ✅ 3 年历史百分位分位数
- ✅ GitHub Actions 每日美股收盘后自动更新
- ✅ Vercel 自动部署

## 本地运行

```bash
pip install -r requirements.txt
python generate_dashboard.py
open index.html
```

## 自动化部署

每个工作日 21:30 UTC（美股收盘后）GitHub Actions 自动执行：
1. 拉取最新期货与 ETF 数据
2. 计算指标与历史分位数
3. 重新生成 `index.html`
4. 推送至 Vercel production

需要在 GitHub Secrets 中配置：`VERCEL_TOKEN` / `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID`
