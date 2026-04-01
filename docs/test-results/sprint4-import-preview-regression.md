# Regression Test Report: Import Preview — Bug Fix Verification
**Date:** 2026-03-31
**Tester:** agent-tester
**Scope:** Regression after Dev fixed BUG #1 and BUG #2 from sprint4-import-preview-qa.md

---

## Test Execution Summary

| Scope | Tests Run | Pass | Fail |
|---|---|---|---|
| BUG #1 regression (session dormitory_id — rooms) | 2 | 2 | 0 |
| BUG #1 regression (session dormitory_id — tenants) | 2 | 2 | 0 |
| BUG #2 regression (old /tenants/import/ URL gone) | 1 | 1 | 0 |
| Full suite (all apps except notifications) | 250 | 250 | 0 |
| **TOTAL** | **250** | **250** | **0** |

Note: apps.notifications excluded — 12 pre-existing errors due to missing `requests` package in venv, unrelated to this feature (unchanged from previous sprint).

---

## BUG #1 Verification — Session Cross-Tab Dormitory Leak

**Status: FIXED**

Checks performed:

1. `test_session_payload_includes_dormitory_id` (ImportRoomsViewTests) — PASS
   Session payload after upload now contains `dormitory_id` key alongside `rows`.

2. `test_confirm_rejects_when_active_dormitory_changed` (ImportRoomsViewTests) — PASS
   When active_dormitory is switched to dorm2 after upload (dorm1), confirm step rejects with redirect and clears the session key `import_rooms_preview`.

3. `test_session_payload_includes_dormitory_id` (ImportTenantsViewTests) — PASS
   Same check for tenant import.

4. `test_confirm_rejects_when_active_dormitory_changed` (ImportTenantsViewTests) — PASS
   Same cross-tab rejection for tenant import.

Code verified in `/srv/letmefix/dms/apps/core/views.py`:
- `_handle_upload` for both views now stores `{'dormitory_id': str(dormitory.pk), 'rows': valid_rows}` in session.
- `_confirm_import` for both views checks `str(dormitory.pk) != payload.get('dormitory_id')` and aborts with error message + session clear if mismatch.

---

## BUG #2 Verification — Old /tenants/import/ URL Removed

**Status: FIXED**

- `resolve('/tenants/import/')` raises `Resolver404` — URL no longer registered.
- `TenantImportView` is absent from `/srv/letmefix/dms/apps/tenants/views.py`.
- `apps/tenants/urls.py` contains no `import` path.
- New canonical import routes remain accessible:
  - `/import/rooms/` resolves to `core:import_rooms`
  - `/import/tenants/` resolves to `core:import_tenants`

---

## Regression Check — No Regressions

All 250 tests from apps.core, apps.tenants, apps.rooms, apps.billing, apps.maintenance, and apps.dashboard pass without error. No previously passing tests were broken by the fix.

---

## Verdict

PASS — Both bugs confirmed fixed. No regressions detected. Feature approved.
