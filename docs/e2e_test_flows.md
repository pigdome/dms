# DMS — E2E Test Flows Design

> วันที่ออกแบบ: 2026-04-01  
> สถานะ: Design complete, implementation pending

---

## สถานะ Coverage ปัจจุบัน

**Unit tests** ครอบคลุมดีในระดับ component:
- Billing calculations (calculate_bill, prorated_rent, dunning_trigger_dates, invoice_number)
- Tenant isolation + IDOR protection
- PDPA anonymize method
- Maintenance ticket status + history
- Room isolation
- Dashboard KPI aggregation
- Import views (CSV/Excel rooms + tenants)
- LINE push_text (mocked)

**ยังขาด:** E2E tests ที่ validate cross-module flows ทั้งหมด

---

## Flow 1: Owner Onboarding (Setup Wizard)

**Objective:** Validate the complete onboarding journey from first login to operational dormitory.  
**Actors:** Owner  
**Importance:** CRITICAL  
**Current Coverage:** ❌ ไม่มี (unit test เช็ค permission เท่านั้น)

### Steps
1. Owner registers/logs in for the first time
2. Owner lands on Setup Wizard (`/setup/`)
3. Step 1: Fill dormitory info (name, address, photo, location)
4. Step 2: Create buildings and define floor/room structure
5. Step 3: Configure billing settings (bill_day, grace_days, water_rate, elec_rate)
6. Wizard completes and redirects to Dashboard

### Expected Outcomes
- Dormitory record created with correct fields
- Building, Floor, Room records created under the dormitory
- BillingSettings record created with correct rates
- UserDormitoryRole created linking owner to dormitory
- Dashboard loads with correct KPI (vacant_count = total rooms, overdue = 0, pending_maintenance = 0)
- ActivityLog entries exist for dormitory creation, building creation, billing settings creation

---

## Flow 2: Bulk Import — Rooms then Tenants

**Objective:** Validate importing rooms via Excel, then importing tenants who get assigned to rooms; verify downstream views update correctly.  
**Actors:** Owner  
**Importance:** HIGH  
**Current Coverage:** ⚠️ Import views tested (upload/preview/confirm/error/isolation), but downstream effects not tested

### Steps
1. Owner uploads room Excel file at `/import/rooms/` with 5 rooms across 2 buildings
2. Preview shows 5 valid rows, Owner confirms
3. Owner uploads tenant Excel file at `/import/tenants/` with 3 tenants assigned to 3 of the 5 rooms
4. Preview shows 3 valid rows, Owner confirms
5. Owner navigates to Room List, Tenant List, and Dashboard

### Expected Outcomes
- 5 rooms created (3 occupied, 2 vacant after tenant import)
- 3 CustomUser records with role=tenant created
- 3 TenantProfile records with correct room assignments
- 3 Lease records with status=active
- Room statuses updated (3 occupied, 2 vacant)
- `/rooms/` shows all 5 rooms with correct statuses
- `/tenants/` shows 3 tenants
- `/dashboard/` shows vacant_count=2, occupancy = 60%
- ActivityLog entries for all imports

---

## Flow 3: Meter Reading → Bill → Payment (Core Billing Cycle)

**Objective:** Validate the complete billing cycle from recording meter readings through payment confirmation.  
**Actors:** Staff, Owner, System (Celery), Tenant  
**Importance:** CRITICAL  
**Current Coverage:** ❌ ไม่มี (unit tests เป็น component เท่านั้น, ไม่มี cross-module)

### Steps
1. Staff logs in, navigates to Meter Reading (`/rooms/meter-reading/`)
2. Staff selects room, enters water_prev=100, water_curr=115, elec_prev=500, elec_curr=580
3. Staff submits meter reading
4. Owner/System triggers bill generation for the month (`generate_bills_for_dormitory`)
5. Bill created with water_amt = 15 × water_rate, elec_amt = 80 × elec_rate
6. Bill status = draft → Owner sends it (status = sent)
7. Tenant logs into portal (`/tenant/`), sees the bill with correct breakdown
8. TMR webhook fires with matching invoice_number and amount
9. Payment record created, bill status = paid
10. Owner views Dashboard — revenue reflects the paid bill

### Expected Outcomes
- MeterReading record created with correct prev/curr values
- Bill.water_units = 15, Bill.elec_units = 80
- Bill.total = base_rent + (15 × water_rate) + (80 × elec_rate)
- Bill.invoice_number follows format PREFIX-YYYYMM-SEQ
- Payment.idempotency_key = TMR ref; duplicate webhook returns "already_processed"
- Bill.status transitions: draft → sent → paid
- Dashboard revenue updated
- ActivityLog entries for meter reading, bill creation, payment

---

## Flow 4: Dunning Schedule (Overdue Reminder Chain)

**Objective:** Validate the complete dunning lifecycle from pre-due reminders through post-overdue escalation.  
**Actors:** System (Celery), Owner  
**Importance:** CRITICAL  
**Current Coverage:** ❌ ไม่มี integration test (unit test เฉพาะ calculate trigger dates และ trigger type choices)

### Steps
1. Bill exists with status=sent and due_date = today + 7 days
2. Day -7: Dunning task runs → triggers pre_7d notification
3. Day -3: Dunning task runs → triggers pre_3d notification
4. Day -1: Dunning task runs → triggers pre_1d notification
5. Day 0 (due date): Dunning task runs → triggers due notification
6. Day 0 passes without payment
7. `mark_overdue_bills()` runs → bill.status = overdue
8. Day +1: Dunning task → triggers post_1d notification
9. Day +7: Dunning task → triggers post_7d notification
10. Day +15: Dunning task → triggers post_15d notification

### Expected Outcomes
- 7 DunningLog records created, one per trigger type
- Each DunningLog linked to correct bill
- Bill.status transitions: sent → overdue (after due_date passes)
- LINE push_text called for each trigger (with correct tenant line_id)
- No duplicate DunningLog for same bill + trigger_type (idempotency)
- If tenant has no line_id, DunningLog still created with success=False
- Owner can see dunning history in bill detail

---

## Flow 5: Maintenance Ticket Full Lifecycle

**Objective:** Validate maintenance request from tenant submission through completion with photo evidence.  
**Actors:** Tenant, Staff/Owner  
**Importance:** HIGH  
**Current Coverage:** ⚠️ Unit tests cover creation + status update + history, but no full lifecycle test

### Steps
1. Tenant logs in to portal, navigates to `/tenant/maintenance/`
2. Tenant submits ticket: description="AC not cooling", attaches issue photo
3. Staff logs in, sees ticket in `/maintenance/` with status=new
4. Staff updates status to in_progress with note "Assigned technician Somchai"
5. Staff updates status to waiting_parts with note "Ordered compressor"
6. Staff updates status to completed with note "Fixed", attaches completion photo
7. Tenant checks portal — sees updated status and full history

### Expected Outcomes
- Ticket created with room from tenant's active lease (not legacy profile.room)
- TicketPhoto records: 1 issue-stage photo, 1 completion-stage photo
- TicketStatusHistory has 4 entries: new → in_progress → waiting_parts → completed
- Each history entry records changed_by, changed_at, note
- Tenant portal shows correct current status and history timeline
- Dashboard pending_maintenance count decreases by 1 after completion
- Ticket from dorm_b not visible to dorm_a staff (isolation maintained throughout)

---

## Flow 6: Parcel Logging and Notification

**Objective:** Validate parcel intake, tenant notification via LINE, and parcel history visibility.  
**Actors:** Staff, Tenant  
**Importance:** MEDIUM  
**Current Coverage:** ❌ ไม่มี (แม้แต่ unit test ก็ยังขาด — significant gap)

### Steps
1. Staff logs in, navigates to `/notifications/parcels/`
2. Staff selects room, enters carrier="Kerry Express", takes photo, adds notes
3. Staff submits parcel log
4. System sends LINE notification to tenant of that room
5. Staff views parcel history at `/notifications/parcels/history/`

### Expected Outcomes
- Parcel record created with room, carrier, photo, notes, logged_by=staff
- Parcel.notified_at populated after LINE notification sent
- LINE push_text called with tenant's line_id and parcel message
- Parcel history shows entry with correct room number, carrier, timestamp
- Parcel from dorm_b not visible to dorm_a staff (isolation)
- If tenant has no line_id, parcel still created but notified_at = null

---

## Flow 7: Broadcast Messaging

**Objective:** Validate broadcast creation and delivery to correct audience segments.  
**Actors:** Owner/Staff  
**Importance:** MEDIUM  
**Current Coverage:** ❌ ไม่มี (แม้แต่ unit test ก็ยังขาด — significant gap)

### Steps
1. Owner creates broadcast: audience_type=all → delivers to all tenants in dormitory
2. Owner creates broadcast: audience_type=building, selects Building A → delivers only to Building A tenants
3. Owner creates broadcast: audience_type=floor, selects Building A Floor 2 → delivers only to that floor

### Expected Outcomes
- Broadcast records created with correct audience_type, title, body
- Broadcast.sent_at populated after delivery
- audience_type=all: LINE sent to all tenants with line_id in dormitory
- audience_type=building: LINE sent only to tenants in selected building
- audience_type=floor: LINE sent only to tenants on selected floor
- Broadcast from dorm_b not visible to dorm_a owner
- ActivityLog entry for each broadcast sent

---

## Flow 8: Multi-Property Owner Switching

**Objective:** Validate that after switching properties, ALL views (not just dashboard) scope correctly.  
**Actors:** Owner  
**Importance:** HIGH  
**Current Coverage:** ⚠️ Unit tests cover property_switch_view + middleware + dashboard, but not all views

### Steps
1. Owner has UserDormitoryRole for Dorm A (primary) and Dorm B
2. Owner logs in → defaults to Dorm A
3. Owner views rooms, billing, tenants, maintenance → all scoped to Dorm A
4. Owner switches to Dorm B via `/property/switch/`
5. Owner views rooms, billing, tenants, maintenance, reports, dashboard → all scoped to Dorm B

### Expected Outcomes
- Session active_dormitory_id updates after switch
- All views respect new dormitory scope (no data from Dorm A visible)
- No data leak from Dorm A after switching to Dorm B
- Switching to dormitory without UserDormitoryRole is rejected (403)
- Import operations respect active dormitory

---

## Flow 9: PDPA Right to be Forgotten (Cascading Effects)

**Objective:** Validate complete tenant data anonymization including cascading effects on room, lease, billing, and maintenance.  
**Actors:** Owner  
**Importance:** HIGH  
**Current Coverage:** ⚠️ Strong unit tests on anonymize() method and view, but cascade effects not tested

### Steps
1. Tenant exists with active lease, phone, line_id, id_card_no, associated bills and maintenance tickets
2. Owner navigates to tenant profile, clicks anonymize
3. Owner confirms anonymization

### Expected Outcomes
- TenantProfile: phone='', line_id='', id_card_no='[REDACTED]'
- TenantProfile.is_deleted=True, deleted_at and anonymized_at populated
- Active lease ends (status → ended)
- Room status changes to vacant
- Tenant no longer appears in `/tenants/` active list
- Historical bills remain intact (not deleted — for accounting)
- Maintenance tickets remain (reporter info anonymized)
- Dashboard occupancy count reflects the vacancy
- ActivityLog entry with action='pdpa_anonymize'
- Future dunning for this tenant's bills stops

---

## Flow 10: Tenant Portal Complete Journey

**Objective:** Validate the full tenant self-service experience.  
**Actors:** Tenant  
**Importance:** HIGH  
**Current Coverage:** ❌ ไม่มี full journey test

### Steps
1. Tenant logs in → lands on portal home (`/tenant/`)
2. Portal shows current room info, latest bill summary, pending maintenance
3. Tenant views bill detail — sees breakdown (base_rent, water, electricity, extras)
4. Tenant submits maintenance request
5. Tenant views maintenance history with status updates
6. Tenant views received parcels
7. Tenant views/edits own profile

### Expected Outcomes
- Portal home shows correct room from active lease (not legacy profile.room)
- Bill breakdown matches calculate_bill output
- Tenant can only see own bills, tickets, parcels, and profile
- Tenant without active lease sees appropriate message
- Tenant accessing staff URLs (`/rooms/`, `/billing/`, `/maintenance/`, etc.) gets 403
- Tenant accessing another tenant's profile gets redirected to own profile

---

## Flow 11: CSV/Report Export Accuracy

**Objective:** Validate that exported CSV content and Report view data match actual database state.  
**Actors:** Owner  
**Importance:** MEDIUM  
**Current Coverage:** ❌ Permission check only, no content validation

### Steps
1. Setup: 2 buildings, 5 rooms each, mix of paid/overdue/draft bills across 2 months
2. Owner exports current month CSV at `/billing/export/`
3. Owner exports previous month CSV
4. Owner views `/reports/` for current and previous month

### Expected Outcomes
- CSV contains correct columns (invoice_number, room, tenant, amounts, status)
- CSV row count matches bill count for filtered month
- CSV totals match Report view totals
- Revenue in report = sum of paid bill totals for the month
- Outstanding in report = sum of overdue bill totals
- Occupancy % = occupied_rooms / total_rooms × 100
- Building-level breakdown correct in report
- Data scoped to active dormitory only

---

## Flow 12: Activity Audit Trail Completeness

**Objective:** Validate that all significant operations generate correct audit log entries.  
**Actors:** Owner, Staff, System  
**Importance:** MEDIUM  
**Current Coverage:** ⚠️ Unit tests cover room CRUD + audit isolation, but not all auditable operations

### Steps
1. Owner creates a room
2. Staff records a meter reading
3. System generates bills
4. Staff creates a maintenance ticket
5. Staff updates ticket status
6. Owner changes billing settings
7. Owner imports tenants
8. Owner anonymizes a tenant
9. TMR webhook processes a payment
10. Owner views `/audit-log/`

### Expected Outcomes
- Each operation produces an ActivityLog entry with correct user, action, detail, dormitory
- System actions have correct attribution (null or system user)
- Audit log view shows entries in reverse chronological order
- Audit log scoped to active dormitory
- Staff cannot access audit log (403)
- Tenant cannot access audit log (403)

---

## Priority & Implementation Order

| Priority | Flow | Gap Severity |
|---|---|---|
| CRITICAL | Flow 3: Meter → Bill → Payment | No cross-module test |
| CRITICAL | Flow 4: Dunning Schedule | No integration test |
| CRITICAL | Flow 1: Setup Wizard | No multi-step test |
| HIGH | Flow 5: Maintenance Lifecycle | Unit only, no full cycle |
| HIGH | Flow 2: Bulk Import → Downstream | Import tested, downstream not |
| HIGH | Flow 8: Multi-Property Switching | Partial coverage |
| HIGH | Flow 9: PDPA Cascading Effects | Model tested, cascade not |
| HIGH | Flow 10: Tenant Portal Journey | No full journey test |
| MEDIUM | Flow 6: Parcel Logging | No tests at all |
| MEDIUM | Flow 7: Broadcast Messaging | No tests at all |
| MEDIUM | Flow 11: CSV Export Accuracy | Permission only |
| MEDIUM | Flow 12: Audit Trail | CRUD only, not completeness |

### แนะนำลำดับ implement
```
Flow 3 (Billing Cycle)  ← เริ่มที่นี่
Flow 4 (Dunning)
Flow 1 (Setup Wizard)
Flow 6 (Parcel)
Flow 7 (Broadcast)
Flow 5 (Maintenance)
Flow 9 (PDPA)
Flow 10 (Tenant Portal)
Flow 8 (Multi-Property)
Flow 2 (Bulk Import)
Flow 11 (CSV Export)
Flow 12 (Audit Trail)
```

### ที่ตั้ง test files แนะนำ
```
apps/
├── billing/tests.py        → Flow 3, 4, 11 (billing-related)
├── core/tests.py           → Flow 1, 2, 8, 12
├── maintenance/tests.py    → Flow 5
├── notifications/tests.py  → Flow 6, 7
├── tenants/tests.py        → Flow 9, 10
```

หรือสร้าง integration test file แยก:
```
tests/
└── integration/
    ├── test_billing_cycle.py      → Flow 3
    ├── test_dunning.py            → Flow 4
    ├── test_setup_wizard.py       → Flow 1
    ├── test_maintenance_flow.py   → Flow 5
    ├── test_parcel_broadcast.py   → Flow 6, 7
    ├── test_multi_property.py     → Flow 8
    ├── test_pdpa.py               → Flow 9
    ├── test_tenant_portal.py      → Flow 10
    ├── test_import_flow.py        → Flow 2
    ├── test_csv_report.py         → Flow 11
    └── test_audit_trail.py        → Flow 12
```
