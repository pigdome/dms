# QA Report: Import Preview Feature (2-Step Flow)
**Date:** 2026-03-31  
**Tester:** agent-tester  
**Feature:** Import Rooms & Import Tenants — Upload+Preview → Confirm+Import  
**Scope:** /import/rooms/ (core:import_rooms) and /import/tenants/ (core:import_tenants)

---

## Test Execution Summary

| Category | Tests Run | Pass | Fail | Error |
|---|---|---|---|---|
| Import Rooms (functional) | 16 | 16 | 0 | 0 |
| Import Tenants (functional) | 14 | 14 | 0 | 0 |
| Partial Preview (rooms) | 5 | 5 | 0 | 0 |
| Partial Preview (tenants) | 4 | 4 | 0 | 0 |
| Other core/rooms/tenants/billing/maintenance/dashboard | 213 | 213 | 0 | 0 |
| **TOTAL** | **252** | **252** | **0** | **0** |

Note: apps.notifications tests have 12 errors due to missing `requests` package in venv — unrelated to this feature, pre-existing issue.

---

## Feature Coverage — Verified Pass

- GET /import/rooms/ and /import/tenants/ return 200 (authenticated owner)
- Unauthenticated requests redirect to /login/
- Staff role gets 403 (OwnerRequiredMixin enforced)
- POST action=download returns valid .xlsx template
- Upload valid .xlsx shows preview_rows in context
- Preview stored in session after upload
- Missing required column → fatal_error shown, no preview rows
- Invalid status/floor_number/date → appears in error_rows with correct row_num
- Duplicate room in file → error_rows
- Room already in DB → error_rows
- Room not in dormitory → error_rows
- Mixed file shows both valid and error rows simultaneously
- Session stores ONLY valid rows (not error rows)
- Preview table shows maximum 10 rows, preview_count shows total valid count
- Confirm creates rooms / user+profile+lease in DB (atomic transaction)
- Room status updated to 'occupied' after tenant import
- Session cleared after successful confirm
- Confirm without session preview redirects gracefully
- Tenant isolation: import scoped to active dormitory only

---

## Bugs Found

### BUG #1
Level: High  
Feature: Import Rooms / Import Tenants — Session Cross-Tab Dormitory Leak  

Steps to reproduce:
1. Owner logs in with access to Dormitory A and Dormitory B
2. Tab A: switch to Dormitory A, navigate to /import/rooms/, upload valid .xlsx file (action=upload) — session now contains import_rooms_preview with rooms intended for Dormitory A
3. Tab B: switch active_dormitory to Dormitory B (POST /core/property/switch/)
4. Tab A or Tab B: POST /import/rooms/ with action=confirm

Result: Rooms from the Dormitory A preview file are created under Dormitory B (the current active_dormitory at confirm time), because _confirm_import reads request.active_dormitory without verifying it matches the dormitory used during upload.

Expected: Confirm step must import only to the dormitory that was active when the file was uploaded. Either (a) store dormitory_id inside the session preview payload and re-verify at confirm, or (b) reject confirm if active_dormitory changed since upload.

Affected files:
- /srv/letmefix/dms/apps/core/views.py — ImportRoomsView._confirm_import (line 645) and ImportTenantsView._confirm_import (line 796)
- Session keys: import_rooms_preview, import_tenants_preview (lines 633, 784)

Root cause: Session preview payload does not store the dormitory_id used during upload. The confirm step blindly trusts request.active_dormitory, which can be switched between upload and confirm steps via /core/property/switch/.

Proof of concept flow:
```
POST /import/rooms/   action=upload  (active_dormitory=DormA) → stores session[import_rooms_preview]
POST /core/property/switch/ dormitory_id=<DormB_pk>           → active_dormitory switches to DormB
POST /import/rooms/   action=confirm (active_dormitory=DormB) → creates rooms in DormB using DormA data
```

---

### BUG #2
Level: Low  
Feature: Import Tenants — Old TenantImportView in tenants/views.py  

Steps to reproduce:
1. Navigate to /tenants/import/ (tenants:import URL)

Result: /tenants/import/ uses the old TenantImportView (apps/tenants/views.py line 160) which is a single-step import — no Preview step. The button label says "Import Now" and it imports immediately on POST without a preview step. This view is still accessible and registered in tenants/urls.py.

Expected: If /tenants/import/ is intentionally kept as a legacy or alternative path, it should either be removed or also updated to use the 2-step preview flow for consistency. Currently two different import UX flows exist for tenant import.

Affected files:
- /srv/letmefix/dms/apps/tenants/views.py — TenantImportView (line 160)
- /srv/letmefix/dms/apps/tenants/urls.py — path('import/', ...) (line 16)
- /srv/letmefix/dms/templates/tenants/import.html — old single-step template

---

## Security Checks

| Check | Result |
|---|---|
| Auth required on all import endpoints | PASS |
| Owner-only (staff blocked) | PASS |
| Tenant cannot access import | PASS |
| Tenant isolation in _parse_tenant_excel (room lookup scoped to dormitory) | PASS |
| Tenant isolation in _parse_room_excel (DB duplicate check scoped to dormitory) | PASS |
| Cross-dormitory import via session cross-tab | FAIL — BUG #1 above |
| Session data cleared after confirm | PASS |
| Atomic transaction (all-or-nothing) | PASS |

---

## Verdict

FAIL — Cannot approve.

BUG #1 (High) must be fixed before approval. The session preview payload must store the dormitory_id used at upload time, and _confirm_import must verify that request.active_dormitory matches it before proceeding.

BUG #2 (Low) should be clarified: either remove the old /tenants/import/ route or migrate it to the same 2-step flow.
