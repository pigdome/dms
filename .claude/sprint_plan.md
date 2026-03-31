# Sprint Plan - Post Pitch Session
Created: 2026-03-30
Updated: 2026-03-31 (Sprint 3 approved)
Approved by: MD
Status: Active

---

## Strategic Context

CC (7 buildings, 300 rooms, budget 15,000-20,000 THB/month) is the highest-value deal.
CC has 2 explicit deal-breakers: **Audit Log** and **Export CSV**.
Conversion likelihood is currently 60% -- lowest among all groups.
This sprint focuses on removing CC blockers first, then addressing CB requirements.

---

## Sprint 1: "Close CC" (Week 1-2, 2026-03-31 to 2026-04-13)

**Status: DONE -- Approved by MD on 2026-03-30**
**Goal:** Remove all CC deal-breakers and raise conversion from 60% to 90%+
**Test Results:** 189/189 tests pass

### Task 1.1 -- Audit Log with Old/New Value Tracking [DONE]
- **Priority:** P0 (CC deal-breaker -- "no audit log = no purchase")
- **Assignee:** @agent-dev (model-architect + backend)
- **Tester:** @agent-tester
- **Status:** DONE -- 186/186 tests pass, IDOR test added
- **Delivered:**
  - ActivityLog extended with `model_name`, `record_id`, `old_value` (JSONField), `new_value` (JSONField)
  - AuditMixin applied to Bill, Payment, Room, TenantProfile, MaintenanceTicket
  - AuditLogView at `/audit-log/` with filters, Owner-only access
  - Tenant isolation verified

### Task 1.2 -- Export CSV with Multi-Month Range [DONE]
- **Priority:** P0 (CC deal-breaker -- "no CSV export = no purchase")
- **Assignee:** @agent-dev (billing-engine)
- **Tester:** @agent-tester
- **Status:** DONE -- 186/186 tests pass
- **Delivered:**
  - Export endpoint at `/billing/export/` with `start_month`, `end_month`, `building_id` params
  - Standard CSV columns, multi-month range, UTF-8 BOM for Thai/Excel
  - Tenant isolation enforced
- **Tech Debt:** N+1 query in CSV export loop -- scheduled for optimization in Sprint 2

### Task 1.3 -- Backend Permission Enforcement [DONE]
- **Priority:** P0 (CB + CC security requirement)
- **Assignee:** @agent-dev (backend)
- **Tester:** @agent-tester (qa focus)
- **Status:** DONE -- 186/186 tests pass + 3 IDOR tests added (189 total)
- **Delivered:**
  - `OwnerRequiredMixin` + `StaffRequiredMixin` created and applied to all views
  - Queryset-level tenant isolation on every view
  - 403 for unauthorized role access
  - IDOR protection tests added after Tester flagged gap

---

## Sprint 2: "Enterprise + CB" (Week 3-4, 2026-04-14 to 2026-04-27)

**Status: DONE -- Approved by MD on 2026-03-31**
**Goal:** Complete CC enterprise features + address CB requirements
**Test Results:** 243/243 tests pass

### Task 2.0 -- Fix N+1 Query in CSV Export (Tech Debt from Sprint 1) [DONE]
- **Priority:** P1 (performance -- affects CC with 500 rooms x 12 months)
- **Assignee:** @agent-dev (billing-engine)
- **Tester:** @agent-tester
- **Status:** DONE -- N+1 fixed with prefetch_related in BillCSVExportView, ReportView optimized with annotate()
- **Delivered:**
  - BillCSVExportView uses `prefetch_related` for room, tenant, building lookups
  - ReportView uses `annotate()` for single-query aggregation
  - Query count is O(1), not O(n)

### Task 2.1 -- Role Hierarchy: Owner > Building Manager > Staff [DONE]
- **Priority:** P1 (CB + CC requirement)
- **Assignee:** @agent-dev (model-architect)
- **Tester:** @agent-tester
- **Status:** DONE -- building_manager role + managed_buildings + BuildingManagerRequiredMixin
- **Delivered:**
  - `building_manager` added to `CustomUser.Role` choices
  - `managed_buildings` M2M field for building-level assignment
  - `BuildingManagerRequiredMixin` enforces building-scope access
  - Building Manager sees only assigned buildings; Owner retains full access

### Task 2.2 -- Report View (Per-Building Breakdown) [DONE]
- **Priority:** P1 (CB + CC requirement)
- **Assignee:** @agent-dev (billing-engine + frontend)
- **Tester:** @agent-tester
- **Status:** DONE -- /reports/ view with per-building revenue/occupancy/outstanding
- **Delivered:**
  - `/reports/` view with per-building cards: revenue, occupancy %, outstanding bills
  - Month filter (default = current month)
  - Tenant isolation enforced
  - BUG #1 found and fixed: N+1 in ReportView resolved with annotate()

### Task 2.3 -- Data Import Wizard (Excel Upload) [DONE]
- **Priority:** P1 (CB + CC requirement)
- **Assignee:** @agent-dev
- **Tester:** @agent-tester
- **Status:** DONE -- /import/rooms/ and /import/tenants/ with validation + atomic transaction
- **Delivered:**
  - `/import/rooms/` and `/import/tenants/` endpoints
  - Downloadable Excel template files
  - Validation: duplicate room numbers, missing required fields
  - Atomic transaction with rollback on partial failure
  - Bug fixed: `_` variable overwrite in import loop

### Task 2.4 -- SMS Notification Channel [DONE]
- **Priority:** P2 (CB requirement)
- **Assignee:** @agent-dev (line-integration team to extend)
- **Tester:** @agent-tester
- **Status:** DONE -- SMSService + notification_channel field + dunning fallback
- **Delivered:**
  - SMSService integration added
  - `notification_channel` field for channel selection (LINE, SMS, both)
  - Dunning fallback logic: if LINE fails, try SMS (configurable)

---

## Sprint 3: "Enterprise Extras" (Week 5-6, 2026-04-28 to 2026-05-11)

**Status: DONE -- Approved by MD on 2026-03-31**
**Goal:** CC enterprise-only features + PDPA compliance
**Test Results:** 263/263 tests pass
**Tester Notes:** 1 Low finding (middleware + Token auth ordering) -- does not affect tenant isolation; acceptable for release.

### Task 3.1 -- REST API Layer (DRF) [DONE]
- **Priority:** P2 (CC only)
- **Assignee:** @agent-dev
- **Tester:** @agent-tester
- **Status:** DONE -- 263/263 tests pass
- **Delivered:**
  - Django REST Framework installed and configured
  - API endpoints for billing data: list bills, bill detail, payment status
  - Token-based authentication (per-dormitory API key)
  - Rate limiting
  - API respects tenant isolation
  - API documentation (Swagger/OpenAPI)

### Task 3.2 -- PDPA: Right to be Forgotten [DONE]
- **Priority:** P2 (CC requirement)
- **Assignee:** @agent-dev
- **Tester:** @agent-tester
- **Status:** DONE -- 263/263 tests pass
- **Delivered:**
  - Soft delete for TenantProfile implemented
  - Data purge mechanism: anonymize personal data after retention period
  - AES-256 encryption on id_card_no field verified
  - Admin action for manual data purge request
  - Purge is irreversible and logged in audit log

### Task 3.3 -- Hosting Info Page + PDPA Documentation [DONE]
- **Priority:** P2 (CA concern + CC requirement)
- **Assignee:** @agent-marketing + @agent-seo
- **Status:** DONE
- **Delivered:**
  - Landing page section explaining data hosting (Thai cloud / on-premise options)
  - PDPA compliance documentation for CC sales process
  - FAQ for CA about hardware requirements (answer: none, web-based)

---

## Dependencies Map

```
Sprint 1 (all parallel within sprint):
  Task 1.1 (Audit Log)      -- no dependency
  Task 1.2 (CSV Export)      -- no dependency
  Task 1.3 (Permissions)     -- no dependency

Sprint 2:
  Task 2.1 (Role Hierarchy)  -- depends on Task 1.3 (permissions framework)
  Task 2.2 (Reports)         -- no dependency
  Task 2.3 (Import Wizard)   -- no dependency
  Task 2.4 (SMS)             -- no dependency

Sprint 3:
  Task 3.1 (REST API)        -- depends on Task 1.3 (permissions)
  Task 3.2 (PDPA)            -- depends on Task 1.1 (audit log for purge logging)
  Task 3.3 (Docs)            -- no dependency
```

---

## Open Questions for Sales Team

Before CC signs, the following must be answered (assigning to @agent-marketing):

1. **SLA:** Do we commit to 99.9% uptime? What is our actual infra capability?
2. **Reference customers:** Can we prepare anonymized demo with 300+ rooms of sample data?
3. **Pricing confirmation:** CA < 500 THB/mo, CB mid-range, CC 15,000-20,000 THB/mo -- are these finalized?

---

## Success Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| CC conversion | 60% -> 90% after Sprint 1, 95%+ after Sprint 3 | All CC blockers removed: Audit Log, CSV Export, REST API, PDPA, Role Hierarchy -- ready to close |
| CB conversion | 80% -> 95% after Sprint 2 | Sprint 2 DONE -- CB features delivered (import, SMS, reports, role hierarchy) |
| CA conversion | 80% -> 90% after Sprint 3 (hosting info) | Sprint 3 DONE -- hosting FAQ and PDPA docs published |
| Sprint 1 delivery | 2026-04-13 | DONE 2026-03-30 (14 days ahead of schedule) |
| Sprint 2 delivery | 2026-04-27 | DONE 2026-03-31 (27 days ahead of schedule) |
| Sprint 3 delivery | 2026-05-11 | DONE 2026-03-31 (41 days ahead of schedule) |
| Total test coverage | Comprehensive | 263 tests, all passing |
