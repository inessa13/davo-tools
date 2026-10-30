---
status: implemented
type: bug
slug: russian-ozon-credit-statements
date: 2026-10-30
---

# Bug: Russian Ozon credit card statements

**Roadmap:** [direct maintenance fix](../roadmap.md)

## Summary

`davo pa ozon2csv` accepts Russian Ozon credit card statements whose header
identifies the credit agreement as `Номер договора`. Existing English
`Account number` and Russian debit-account `Номер лицевого счёта` headers
remain supported.

## Compatibility

The imported `external_id` keeps the existing
`O<account-or-contract>_<document-number>` format. Operation parsing, amounts,
statement-total validation, the CSV schema, and the `personal_site` importer
are unchanged.

## Verification

- Extract a contract number from a Russian `Номер договора` header.
- Parse `examples/20261030/20261030 ozon dzd cc.pdf` as 50 operations and
  verify its deposit and withdrawal totals.
- Preserve the existing IDs produced for the English and Russian debit Ozon
  examples under `examples/20261002/`.
- Run `make test` and `make lint`.
