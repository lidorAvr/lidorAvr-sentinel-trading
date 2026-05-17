# ALGO Reference & Real-Data Review — 2026-05-16 (founder-supplied, authoritative)

> **Source of truth.** Faithful structured capture of the founder's full 5-ALGO review
> (QQQ, TSLA, JPM, HOOD, PLTR), from TrendSpider backtest CSVs. **Caveat (founder's
> own):** data is **backtest, %-per-trade, NO commissions, NO slippage, NO real capital
> allocation**. "Whole portfolio" here = a statistical trade pool, NOT a live account
> performance report. All thresholds the teams derive MUST honor this caveat and
> AGENTS.md #8 (ALGO cohort isolated from headline Win-Rate/Expectancy).

## 1. Per-ALGO strategy rules (the real logic — unblocks #4)

| ALGO | Chart | Entry | Entry filter | Tech exit | Take Profit | Stop Loss | Time exits |
|---|---|---|---|---|---|---|---|
| **QQQ** (Core) | 2h | SMA6 ↑ SMA30 | open > SMA10 | SMA16 ↓ SMA51 | +11% | **none (hard)** | 3c<−2% · 33c<0% · 46c<1.7% · 90c<11% |
| **TSLA** (Aggr.) | 2h | SMA6 ↑ SMA34 | open > SMA15 | SMA5 ↓ SMA34 | +25% | **−4.3%** | — |
| **JPM** (Stab.) | 2h | SMA7 ↑ SMA34 | — | SMA6 ↓ SMA40 | +18% | **−3.3%** | — |
| **HOOD** (Explos.) | 2h | EMA9 ↑ EMA21 | — | EMA21 ↑ EMA9 | +80% | **none (hard)** | 10c<4% · 65c<25% · 85c<40% |
| **PLTR** (HighRisk) | 30m | EMA5 ↑ EMA34 | close ≥ SMA100 | — | +16% (after candle close) | **−25% (emergency cushion, not a mgmt stop)** | 230c if loss>14.8% · 295c if loss>12% |

Key for #4: QQQ & HOOD have **no hard stop** (time-exits are the risk control); PLTR's −25% is an emergency cushion, not a management stop. "InitStop/CurrStop Unknown" for ALGO is wrong — it should reflect *these known rules per symbol*.

## 2. Per-ALGO stats (real backtest)

| ALGO | Trades | Open | Win% | Avg trade | Median | PF | Avg win | Avg loss | R/R | Worst internal DD | Max loss streak | last-5 | last-10 | Role |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| QQQ | 98 | 0 | 46.9% | 1.29% | −0.29% | 2.29 | 4.86% | −1.88% | 2.59 | −7.01% | 7 | +3.35% | +0.72% | Core anchor |
| TSLA | 49 | 1 | 38.8% | 2.78% | −1.21% | 2.45 | 12.13% | −3.14% | 3.87 | −13.17% | 7 | +10.61% | +12.24% | Aggressive momentum |
| JPM | 33 | 0 | 57.6% | 1.89% | 0.33% | 4.23 | 4.31% | −1.38% | 3.12 | −6.83% | 3 | −2.87% | −5.58% | Stabilizer (low alpha) |
| HOOD | 34 | 0 | 52.9% | 8.15% | 1.23% | 7.13 | 17.90% | −2.82% | 6.34 | −11.14% | 4 | −7.55% | +1.97% | Explosive (concentrated) |
| PLTR | 18 | 1 | 72.2% | 10.36% | 15.40% | 4.01 | 19.12% | −12.41% | 1.54 | −24.26% | 2 | −29.86% | +25.26% | High-risk satellite |

**Aggregate (232 trades, 230 closed, 2 open):** Win 49.6% · avg/trade 3.40% · median −0.05% · avg win 9.62% · avg loss −2.72% · **R/R 3.54** · **PF 3.48** · best +85.69% · worst −16.70% · avg internal DD −4.52% · worst −24.26% · max loss streak 12 · avg length 46.5 candles.
**Positive skew:** top-10 trades = 50.2% of all profit; top-5 = 34.4%. Half the return came from 10 of 232 trades.

## 3. Regime by year (THE current-state signal)

| Year | Trades | Return | Win% | PF |
|---|---|---|---|---|
| 2020 | 13 | +37.30% | 76.9% | 5.36 |
| 2021 | 16 | +12.15% | 43.8% | 1.82 |
| 2022 | 18 | −10.95% | 16.7% | 0.67 |
| 2023 | 17 | +39.27% | 58.8% | 3.09 |
| 2024 | 67 | +468.04% | 59.7% | 8.60 |
| 2025 | 74 | +259.42% | 54.1% | 3.19 |
| **2026** | **27** | **−16.65%** | **18.5%** | **0.73** |

**2026 = Yellow/Red regime** (27 trades, 18.5% win, PF<1). 2024 was the golden year; the backtest looks good mostly because of 2024–2025. Recent decay is real and **cluster-wide simultaneously** (QQQ Yellow, TSLA Yellow+profit-guard, JPM Yellow/Red, HOOD Yellow/Red, PLTR Red).

## 4. Exit-type analysis (whole pool)

| Exit | Trades | Total return | Avg | Win% |
|---|---|---|---|---|
| Take Profit | 30 | +672.55% | 22.42% | 100% |
| MA cross | 92 | +133.35% | 1.45% | 50.0% |
| Time exits | 92 | +39.62% | 0.43% | 40.2% |
| Stop / combined | 16 | −65.62% | −4.10% | 6.3% |
| Open | 2 | +8.68% | 4.34% | 50% |

TP is the profit engine; time-exits mostly clear dead trades (low $); stops are the system's cost; PLTR's time-exits fire AFTER deep losses (problematic).

## 5. Founder's recommended exposure (on a ~$7,500 book) + cluster cap

| ALGO | Exposure | ~$ on $7,500 |
|---|---|---|
| QQQ | 6–7% | 450–525 |
| TSLA | 5–7% | 375–525 |
| JPM | 3–5% | 225–375 |
| HOOD | 3–5% | 225–375 |
| PLTR | 1.5–2.5% | 112–188 |

Desired total now ≈ **18.5–26.5%**. Cluster cap: ≤25% OK · 25–30% caution (no add w/o reason) · >30% no new full-size · **>35% Critical**.

## 6. Founder-proposed Risk Governor (§12 — the concrete fine-tuning input for DEC-20260515-014)

**Decay control**
| Trigger | Action |
|---|---|
| PF of last 10 trades < 1 | do not increase exposure |
| last 5 trades negative > 7.5% | cut size 50% |
| last 10 trades negative > 10% | freeze full-size opening |
| 6-loss streak | Yellow |
| 8-loss streak | Red |
| current trading-year negative for the algo | no increase until improvement |

**Open-profit control**
| State | Action |
|---|---|
| open > 7% | tight monitor |
| open > 10% | do not let it return to a full loss |
| open > 15% | lock part of the profit |
| open > 20% | Runner Mode |
| giveback > 50% of peak profit | strong alert |

**Cluster control**
| State | Action |
|---|---|
| several algos open on growth names together | compute Cluster Risk |
| QQQ below key daily MAs | reduce size on the aggressive algos |
| PLTR & HOOD open together | no additional speculative risk |
| TSLA & PLTR open together | check volatile-momentum exposure |
| whole cluster > 30% | block new full-size trades |

## 7. Founder's final verdict (binding intent)

Keep all 5 ALGOs **live**; **do NOT increase exposure now**; Edge exists (mostly via the strong R/R) but is **not currently stable**; 2026 is concerning; **separating manual vs ALGO stats is mandatory** (AGENTS.md #8); a **Risk Governor is mandatory**; PLTR must stay very small; QQQ is the core; TSLA continue w/ profit-guard; JPM = stabilizer not engine; HOOD risky but keep small.

## How the teams must use this
- This file is the authoritative ALGO data. Mark fine-tunes DEC-20260515-014 numbers against §6 here.
- #4 (ALGO data-quality): replace "Unknown" with the §1 known per-symbol stop/exit logic.
- #5 (strategy-adaptive dead-money): each ALGO's §1 time-exits ARE its non-working signal.
- §6 Governor overlaps existing engine signals (Giveback, RUNNER, profit checkpoints, loss-streak) — reuse those, isolate the ALGO cohort (#8), invent no new math.
