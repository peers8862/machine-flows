# Subscriptions (example)

The real file, `ai-tools/SERVICES.md`, holds personal subscription costs and renewal dates, so it stays local. It is generated from a CSV (`ai-tools/sheets/services.csv`), which is the source of truth. This is the shape, with made-up values.

CSV columns: `service,plan,cost,currency,billing_cycle,renews,status,what_it_covers,used_for_in_machine_flows,notes`. A blank cell means unknown.

## Renewals, soonest first

| Renews | Service | Cost | Notes |
| --- | --- | --- | --- |
| 2026-01-15 | Example Editor | 20 | |
| 2026-02-01 | Example Agent | 25 | |

## No renewal

| Service | Status | Notes |
| --- | --- | --- |
| Example Tracker | free | |
| Example Notes App | lifetime licence | |
