# Risk Rules

## Definitions

### Campaign
One trading idea from first entry to final exit.

### Position
Current open broker holding.

### Lot
Broker/accounting unit with quantity, cost and execution information.

### Original Campaign Risk
The planned initial risk of the campaign.

### Current Risk
The remaining live downside risk based on current stop and open quantity.

### Open R
Unrealized result relative to original campaign risk.

### Closed R
Realized result relative to original campaign risk.

### Campaign R
Open R plus Closed R.

## Rules

Partial exits reduce open quantity but do not create new campaigns.

Moving a stop changes current risk but does not change original campaign risk.

Runner positions remain linked to the original campaign.

Protected profit must be shown separately from open unrealized R.

If data is missing, the system must mark it as Unknown or Estimated.
