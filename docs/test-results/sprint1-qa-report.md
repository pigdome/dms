# QA Test Report — Sprint 1 "Close CC"
Date: 2026-03-30
Tester: @agent-tester
Overall Verdict: **PASS with 1 Medium finding**

---

## 1. Test Suite Results

```
Ran 186 tests in 20.235s
OK
System check identified no issues (0 silenced)
```

All 186 tests pass. No failures.

---

## 2. Migration Check

`migrate --check` could not connect to the production DB (PostgreSQL not running outside Docker).
Migration files were verified by file inspection instead.

- `apps/core/migrations/0002_audit_log_old_new_fields.py` — present, adds `model_name`, `record_id`, `old_value`, `new_value` to ActivityLog. Consistent with model definition.
- No unapplied migration files found for any app.

Status: PASS (DB-level apply pending until Docker environment is started)

---

## 3. Acceptance Criteria — Task 1.1: Audit Log

| Criteria | Status | Notes |
|---|---|---|
| ActivityLog has model_name, record_id, old_value, new_value | PASS | apps/core/models.py:145-152 |
| AuditMixin applied to Bill | PASS | apps/billing/models.py:47 |
| AuditMixin applied to Payment | PASS | apps/billing/models.py:162 |
| AuditMixin applied to Room | PASS | apps/rooms/models.py:32 |
| AuditMixin applied to TenantProfile | PASS | apps/tenants/models.py:7 |
| AuditMixin applied to MaintenanceTicket | PASS | apps/maintenance/models.py:7 |
| AuditLogView owner/superadmin only | PASS | OwnerRequiredMixin applied at apps/core/views.py:191 |
| Anonymous → redirect to login | PASS | Tested in AuditLogViewAccessTests |
| Tenant role → 403 | PASS | Tested in AuditLogViewAccessTests |
| Staff role → 403 | PASS | Tested in AuditLogViewAccessTests |
| Tenant isolation: owner A ≠ owner B logs | PASS | AuditLogTenantIsolationTests covers both via view and direct DB |
| create log: old_value=None, new_value=snapshot | PASS | AuditMixinRoomTests.test_create_room_generates_audit_entry |
| update log: only changed fields | PASS | AuditMixinRoomTests.test_update_room_logs_changed_fields_only |
| delete log: old_value=snapshot, new_value=None | PASS | AuditMixinRoomTests.test_delete_room_logs_old_value |
| no-change save → no update log | PASS | AuditMixinRoomTests.test_no_audit_log_when_no_real_change |

Task 1.1: **PASS**

---

## 4. Acceptance Criteria — Task 1.2: BillCSVExportView

| Criteria | Status | Notes |
|---|---|---|
| URL /billing/export/ exists | PASS | apps/billing/urls.py wired to BillCSVExportView |
| No start_month param → show form | PASS | apps/billing/views.py:233-241 |
| Single month export (start = end) | PASS | BillCSVExportViewTests coverage |
| Multi-month range filter | PASS | BillCSVExportViewTests.test_multi_month_range |
| Building filter (building_id param) | PASS | apps/billing/views.py:281-282 |
| UTF-8 BOM written at head of file | PASS | apps/billing/views.py:291 (`response.write('\ufeff')`) |
| Tenant isolation enforced | PASS | dormitory filter applied before building filter; BillCSVExportViewTests.test_tenant_isolation |
| start > end swapped (no crash) | PASS | apps/billing/views.py:261-262 |
| Invalid date format → redirect with error | PASS | apps/billing/views.py:247-255 |
| Owner-only access (staff → 403) | PASS | OwnerRequiredMixin; StaffAccessOwnerOnlyTests.test_staff_bill_export_forbidden |

Task 1.2: **PASS**

---

## 5. Acceptance Criteria — Task 1.3: Permissions

| Criteria | Status | Notes |
|---|---|---|
| OwnerRequiredMixin in apps/core/mixins.py | PASS | apps/core/mixins.py:33 |
| StaffRequiredMixin in apps/core/mixins.py | PASS | apps/core/mixins.py:54 |
| Anonymous → redirect to login (all views) | PASS | AnonymousAccessTests covers 14 URLs |
| Tenant → 403 on staff/owner views | PASS | TenantAccessDeniedTests covers 8 URLs |
| Staff → 403 on owner-only views | PASS | StaffAccessOwnerOnlyTests covers 4 URLs |
| Staff → 200 on staff-allowed views | PASS | StaffAccessAllowedTests covers 5 URLs |
| Owner → 200 on all views | PASS | OwnerAccessAllowedTests covers 6 URLs |
| Tenant isolation across dormitories | PASS | TenantIsolationTests covers rooms, tickets, tenants, room detail IDOR |

Task 1.3: **PASS**

---

## 6. Bugs Found

### BUG #1
Level: Medium
Feature: Task 1.3 — Permissions / TenantDetailView
File: apps/tenants/views.py:49

Description:
TenantDetailView uses only `LoginRequiredMixin`, not `StaffRequiredMixin`.
The view contains manual role logic (line 52: `if request.user.role == 'tenant':`)
that correctly redirects a tenant to their own profile. The staff/owner path
correctly scopes by dormitory using `get_object_or_404` + `_dorm_profiles()`.

However, there is no explicit test in the permission test file covering:
- A tenant user attempting to access another tenant's UUID directly at
  `/tenants/<other_uuid>/`

The code redirects them correctly (own_profile.pk != pk → redirect), but this
test case is absent from the regression suite, leaving a gap in coverage.

Steps to reproduce:
1. Login as tenant user A who has profile UUID = X
2. GET /tenants/<UUID of tenant B>/
Expected: redirect to /tenants/<UUID of A>/
Actual (from code logic): redirect happens correctly per line 57-58, but
there is no automated test to prevent regression.

Recommendation: Add a test to `tests_permissions.py` covering this IDOR
redirect for tenant users.

---

## 7. Code Quality

- No raw SQL found
- No obvious N+1 queries in the three new views (CSV export uses select_related,
  AuditLogView uses select_related, no loops calling DB inside row iteration
  except for tenant_name lookup in CSV export which queries leases per bill — see note below)
- Security: No sensitive fields exposed. id_card_no is encrypted per TenantProfile
- Webhook idempotency: implemented correctly via `idempotency_key` uniqueness check
  before transaction (apps/billing/views.py:179)

### Note — CSV Export: per-bill DB query for tenant name
File: apps/billing/views.py:304-309

Inside the CSV row loop, for each bill:
```python
active_lease = b.room.leases.filter(status='active').select_related(...)first()
if active_lease:
    tenant_name = active_lease.tenant.full_name
else:
    profile = b.room.tenant_profiles.select_related('user').first()
```

This issues up to 2 extra queries per bill row. For large exports (hundreds of rows)
this is a potential N+1 concern. Not Critical since this is owner-only, async
is not needed, and the data size is bounded per export range. Recommend a future
optimization with prefetch_related on the initial queryset.

This is rated Low severity and does not block Sprint 1 approval.

---

## 8. Overall Verdict

| Task | Result |
|---|---|
| Task 1.1 — Audit Log | PASS |
| Task 1.2 — CSV Export | PASS |
| Task 1.3 — Permissions | PASS |
| Full test suite (186 tests) | PASS |
| Security / IDOR check | PASS (1 missing test case — BUG #1 Medium) |

**Sprint 1: PASS**

BUG #1 (Medium) is a missing regression test, not a functional defect. The code
behaves correctly. Recommend Dev adds the test case before the next sprint to
prevent regression.
