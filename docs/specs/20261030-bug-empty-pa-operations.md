---
status: implemented
type: bug
slug: empty-pa-operations
date: 2026-10-30
---

# Bug: empty personal-accounting operations

**Roadmap:** [direct maintenance fix](../roadmap.md)

## Summary

For Sber card statements, use the first description line (`source_category`)
as a fallback whenever configured rules leave `Операция` empty. Apply the
fallback to both incoming and outgoing card operations.

Before planning any CSV writes, reject remaining empty or whitespace-only
operations produced by the Sber, T-Bank, or Ozon converters. Report every
invalid row together in one error, including its source path, date, and
`external_id`.

## Compatibility and safety

- Keep the CSV schema, amount reconciliation, and `personal_site` unchanged.
- Keep Sber place and category values already extracted by rules.
- Do not fall back to the full raw description when `source_category` is
  unavailable.
- Empty place, category, and comment values remain valid.
- Validate a whole invocation, including `--dry-run`, before creating or
  replacing any CSV so mixed valid/invalid batches cannot produce partial
  output.

## Verification

- Cover a Sber `Перевод с карты SBOL...` rule result whose fallback operation
  becomes `Перевод с карты`, preserving `SBOL` and `__tr__`.
- Cover incoming and outgoing Sber card fallbacks.
- Reject Sber rows without a fallback and empty T-Bank/Ozon operations.
- Verify all three commands write nothing for invalid operations, including a
  mixed valid/invalid batch and `--dry-run`.
- Keep tests independent from `examples/`; use supplied MIR/Visa documents only
  for manual verification.
- Run the PA tests, scoped lint, `make test`, and `make lint`, reporting any
  unrelated pre-existing failures separately.
