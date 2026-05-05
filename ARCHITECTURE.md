# Architecture

## High-Level Flow

Broker / IBKR
-> raw positions and executions
-> normalized positions and lots
-> campaigns
-> risk calculations
-> exposure calculations
-> reports
-> Telegram / dashboard

## Module Responsibilities

### broker/
Responsible for broker integration, IBKR sync, raw positions, executions and order state.

### portfolio/
Responsible for positions, lots, campaign truth, partial exits and cost basis.

### risk/
Responsible for risk governor, R calculations, current risk, original risk, drawdown, exposure and allowed risk mode.

### strategies/
Responsible for EP, VCP and ALGO classification.

### reporting/
Responsible for Telegram messages, dashboard text and user-facing reports.

Important:
reporting/ may display calculated values, but must not calculate financial truth.

### storage/
Responsible for Supabase/database access and persistence.

## Boundaries
- broker/ must not decide trade quality.
- reporting/ must not calculate R or PnL truth.
- risk/ must not fetch raw broker data directly.
- portfolio/ owns campaign and lot truth.
