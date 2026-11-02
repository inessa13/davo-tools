---
status: implemented
type: feature
slug: revolut-pdf-csv
date: 2026-11-02
---

# Revolut PDF to CSV

**Roadmap:** [direct feature request](../roadmap.md)

## Summary

`davo pa revo2csv PATH... [-o FILE] [-0] [-v] [-W]` converts Russian and
English Revolut current-account PDF statements to the fixed Russian-column CSV
accepted by `RevolutImporterV3Ru`. Automatic targets use `<stem>.csv`; batch,
dry-run, explicit-output, and rewrite behaviour matches the other `pa *2csv`
commands.

The user explicitly allowed this specification and implementation to be added
in one commit as an exception to the normal spec-only commit boundary.

## Output contract

The UTF-8 file has no BOM and uses these columns in order:

`Тип,Продукт,Дата начала,Дата выполнения,Описание,Сумма,Комиссия,Валюта,State,Остаток средств`

- Card operations become `Платеж по карте`, transfers become `Переводы`, and
  an unrecognised type stays empty.
- Product is `Текущий`, fee is `0.00`, and state is `ВЫПОЛНЕНО`.
- The PDF date is copied to both date columns at `00:00:00`; money out is
  negative and money in is positive.
- Description text and the three-letter statement currency are preserved.

## Parsing and safety

The supported templates are identified by their localized statement, balance,
and transaction headings. Russian and English month names and amount formats
are accepted. Repeated transaction headers on continuation pages are parsed;
other layouts fail explicitly.

Before output, the converter checks the opening/closing equation, account and
total summary rows, total money out/in, and every transaction balance. Every
input in a batch is parsed and reconciled before any target is written. An
explicit target is never overwritten; `--rewrite` applies only to automatic
targets.

The PDF does not contain the original transaction times or separate start
dates. Statements are limited to one completed current-account currency.

## Verification

- Synthetic Russian and English pages cover card payments, transfers, unknown
  types, localized months/numbers, continuation headers, and CSV quoting.
- Structure, totals, running-balance, atomic-batch, dry-run, rewrite, and CLI
  failures are tested without depending on `examples/`.
- The checked-in Russian and English PDFs are compared manually with their CSV
  exports by calendar date, description, type, amount, currency, and balance.
- Generated CSV is checked with `RevolutImporterV3Ru`; PA/CLI tests, scoped
  lint, `make test`, and `make lint` are run, with unrelated baseline failures
  reported separately.
