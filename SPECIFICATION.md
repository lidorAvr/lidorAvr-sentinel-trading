# Sentinel Trader - Specification

## Purpose
Sentinel Trader is a trading management and risk-control system.

The system tracks:
- open positions
- trading campaigns
- partial exits
- open R
- closed R
- campaign R
- current risk
- original campaign risk
- exposure
- market regime
- Telegram reports
- IBKR/Supabase sync where applicable

## Core Principle
The system is a risk manager first and a reporting bot second.

Reporting modules may display values, but must not create financial truth.

## Strategies
- EP: Event / Earnings Play
- VCP: Volatility Contraction Pattern
- ALGO: Automated strategy bucket

## Capital Baseline
- Base Capital: 7500 USD
- Default risk per trade: 0.50%
- Defensive risk per trade: 0.35%

## R Rules
- R is calculated from the original planned campaign risk unless explicitly stated otherwise.
- Moving a stop does not rewrite original risk.
- Partial exits do not create new campaigns.
- Runner positions remain part of the original campaign.
- Open R and Closed R must be separated.
- Campaign R equals realized plus unrealized result relative to original campaign risk.

## Data Scope Mode
If only YTD data exists, all performance metrics must be labeled YTD.
The system must not infer full-history trader performance from partial broker data.

Allowed scopes:
- YTD
- Since Import
- Full History
- Estimated
- Unknown

## ALGO Caps
- QQQ: 10%
- TSLA: 7%
- JPM: 7%
- PLTR: 6%
- HOOD: 6%

ALGO cluster warning: 30%
ALGO cluster critical: 35%

## Safety Rules
- Never change financial calculations and Telegram formatting in the same task.
- Never change database schema without explicit migration plan.
- Never touch production secrets.
- Never assume missing broker data.
- Any change to R, PnL, exposure, lots, campaigns, partial exits, broker sync or risk requires tests.
