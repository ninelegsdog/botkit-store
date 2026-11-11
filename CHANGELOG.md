# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### Added

- `src/store/texts.py` — single source for user-facing strings. A reply used to
  live as a literal inside `message.answer(...)` and was duplicated in the e2e
  test and in the farm's `cases/*.yaml`; three copies of one phrase drift on the
  first edit. Handlers, `core/navigation.py` and the e2e test now import the
  constants. `tests/test_texts_contract.py` guards it, including negative twins:
  a helper that drops its argument goes red.
- **Admin catalogue management** (`admin/handlers.py`, `core/navigation.py`,
  `core/fsm.py`, `core/ui.py`, `store/service.py`, `store/texts.py`): full CRUD
  for categories and products from the bot chat — create/edit/toggle/delete,
  key-pool replenishment, stock alerts, order manual-fulfil/cancel/refund.
  All destructive actions require `✅ Да` / `❌ Нет` confirmation.
- Service layer: `update_category`, `delete_category`, `toggle_category`,
  `get_categories_admin`, `update_product`, `delete_product`, `toggle_product`,
  `get_product_admin`, `add_keys`, `get_stock`, `manual_fulfill_order`,
  `cancel_order`, `refund_order`, `get_orders_by_status`,
  `get_orders_for_user`, `get_sales_stats`, `get_low_stock_products`.
- FSM state groups: `AdminCategory`, `AdminProduct`, `AdminOrder` with
  multi-step flows for creating/editing categories, products and fulfilling orders.
- 41 new tests covering service CRUD, admin handler flows, negative scenarios
  and contract compliance (`test_service_admin.py`, `test_admin_handlers.py`,
  `test_admin_handler_direct.py`, `test_admin_handler_coverage.py`). A reply used to
  live as a literal inside `message.answer(...)` and was duplicated in the e2e
  test and in the farm's `cases/*.yaml`; three copies of one phrase drift on the
  first edit. Handlers, `core/navigation.py` and the e2e test now import the
  constants. `tests/test_texts_contract.py` guards it, including negative twins:
  a helper that drops its argument goes red.
- The repository presents itself as it is. The README became a front page — pitch,
  badges, a table of contents and user-facing sections — and issue forms plus a
  pull-request template now ask for the evidence this project acts on: what was
  run, what was expected, and how "done" would be able to fail.
- Governance layer brought to the family standard: `CONTRIBUTING.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, `AGENTS.md`, `.editorconfig`,
  `.gitattributes` and `CODEOWNERS`.
- `scripts/check-repo-contract.py` checks this repository against the shared
  contract, and `scripts/check-repo-contract_test.py` proves that checker can
  fail. A gate that has never gone red is an assumption, not a gate.

### Fixed

- `README-testing.md` was unreachable from the README in every bot of the family
  except one. A document nobody can reach is a document nobody reads; it is linked
  from the front page now.

### Changed

- Line endings are pinned to LF by `.gitattributes`, so a CRLF contributor no
  longer turns every touched line into a diff.

## [1.0.0] — 2026-10-13

Project running in production. See the git history for the work preceding this
entry; the changelog starts here because the repository had none.
