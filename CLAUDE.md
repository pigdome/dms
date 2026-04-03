# DMS — Dormitory Management System

## Project Overview
ระบบบริหารจัดการหอพัก Multi-Tenant SaaS สำหรับเจ้าของหอพักไทย รองรับตั้งแต่หอเล็ก 10 ห้อง จนถึงหอใหญ่ 500+ ห้อง
ดู spec เต็มได้ที่ [instruction.md](instruction.md)

---

## Tech Stack
- **Backend:** Django + Django Admin (theme: unfold)
- **Frontend:** Django Templates (Owner/Staff web + Tenant portal)
- **Database:** PostgreSQL + Prisma ORM
- **Cache/Queue:** Redis + Celery + django-celery-beat
- **File Storage:** Local filesystem
- **Hosting:** Docker + Docker Compose
- **Payment:** TMR Payment Gateway (PromptPay QR + Webhook)
- **Notifications:** LINE Messaging API

---

## Architecture Decisions
- **Multi-Tenancy:** `tenant_id` ต้องอยู่ใน **ทุก Model** ที่มีข้อมูลของ Owner — ห้าม query ข้าม tenant โดยเด็ดขาด
- **Django Apps:** แยก app ตาม domain (billing, rooms, tenants, maintenance, notifications, etc.)
- **Background Jobs:** ใช้ Redis + Celery สำหรับ Dunning, LINE notifications
- **Webhook:** Payment webhook ต้องรองรับ Idempotency (ป้องกัน double-process)

---

## AI Agent Architecture

**Claude** = Orchestrator (reasoning, coding, decision making)
**Gemini** = Context Synthesizer (file discovery, large-scale reading)

### เมื่อไหร่ให้เรียก Gemini
✅ ควรเรียก:
- ต้องค้นหาว่า topic/keyword อยู่ในไฟล์ไหน และต้องค้นหาหลายไฟล์
- ต้องอ่าน markdown/text files จำนวนมากพร้อมกัน
- ต้องทำ cross-file analysis หรือ summarize ก่อนที่ Claude จะอ่านจริง

❌ ไม่ต้องเรียก:
- ไฟล์น้อย หรือรู้ path อยู่แล้ว (อ่านเองเร็วกว่า)
- งานต้องการ reasoning หรือ coding จริงจัง
- task ง่ายหรือ context ชัดเจนอยู่แล้ว

### วิธีเรียก Gemini
```bash
gemini -p "YOUR_PROMPT_HERE"
# หรือผ่าน script กลาง
bash scripts/ask-gemini.sh "YOUR_PROMPT_HERE"
```

### Workflow มาตรฐาน
1. เรียก Gemini → "ใน folder นี้ มีไฟล์ไหนที่เกี่ยวกับ [topic] บ้าง?"
2. รับรายชื่อไฟล์กลับมา
3. **Verify** ว่าไฟล์นั้นมีอยู่จริง (Glob หรือ Read) ก่อนใช้เสมอ
4. Claude อ่านเฉพาะไฟล์ที่จำเป็น

> Gemini output ใช้เป็น **reference เท่านั้น** — ไม่ใช่ source of truth

---

## User Roles
| Role | คำอธิบาย |
|---|---|
| `superadmin` | System owner — จัดการ Owner accounts |
| `owner` | เจ้าของหอพัก — จัดการหอ/ตึก/ห้อง/ผู้เช่าของตัวเอง |
| `staff` | พนักงานหอ — สิทธิ์จำกัดตามที่ Owner กำหนด |
| `tenant` | ผู้เช่า — เข้าผ่าน tenant portal (`/tenant/`) |

---

## Coding Conventions
- ใช้ภาษา **English** สำหรับ code, variable names, comments, model fields
- Django template i18n-ready: ใช้ `{% trans %}` สำหรับ user-facing text ทุกจุด
- Model ทุกตัวที่ผูกกับ Owner ต้องมี `tenant` ForeignKey
- ใช้ Django ORM — ห้าม raw SQL ยกเว้นจำเป็นจริงๆ
- View ทุกตัวต้อง enforce tenant scope (ใช้ mixin หรือ queryset filter ที่ base level)
- เขียน test สำหรับ billing calculation และ payment webhook เสมอ
- Comment business logic สำคัญเป็นภาษาไทยได้ เพื่อให้ทีมเข้าใจง่าย
- ทุก PR ต้องมี test case

---

## Key Files & Structure
```
dms/
├── CLAUDE.md
├── instruction.md
├── design/                    # UI mockups (reference only, do not modify)
│   └── stitch/                # complete screen designs (12 screens)
├── docker-compose.yml
├── Dockerfile
├── .env / .env.example
├── requirements.txt
├── manage.py
├── config/                    # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── celery.py
└── apps/
    ├── core/          # Dormitory (tenant), CustomUser (role), ActivityLog
    ├── billing/       # Bill, Payment, TMR webhook, billing settings
    ├── rooms/         # Building, Floor, Room, MeterReading
    ├── tenants/       # TenantProfile, Lease, DigitalVault
    ├── maintenance/   # MaintenanceTicket, TicketStatusHistory
    ├── notifications/ # LineMessage, Parcel, DunningSchedule, Broadcast
    └── dashboard/     # views only (aggregates from other apps)
```

## UI Screens (design/stitch/)
Reference สำหรับ frontend agent — ทุกหน้ามี `code.html` (Tailwind) และ `screen.png`:

| Screen | Path | User |
|---|---|---|
| Owner Dashboard | `owner_dashboard/` | Owner |
| Room Management | `room_management_owner/` | Owner |
| Meter Reading Wizard | `meter_reading_wizard/` | Staff |
| Maintenance Ticket List | `maintenance_tickets_owner/` | Owner/Staff |
| Maintenance Ticket Detail | `maintenance_ticket_detail/` | Owner/Staff |
| Parcel Logging | `parcel_logging_staff/` | Staff |
| Tenant Profile & History | `tenant_profile_history/` | Owner |
| Tenant Portal (Home) | `tenant_view_line_mini_app/` | Tenant |
| Add/Import Tenants | `add_import_tenants/` | Owner |
| Broadcast Creator | `broadcast_creator/` | Owner |
| Payment & Billing Settings | `payment_billing_settings/` | Owner |
| Setup Wizard | `setup_wizard_owner/` | Owner (onboarding) |

---

## Core Data Models (derived from design screens)

```
core:       Dormitory(name, address, photo, location), CustomUser(role, dormitory_fk), ActivityLog
rooms:      Building(dormitory_fk, name), Floor(building_fk, number), Room(floor_fk, number, status*)
            MeterReading(room_fk, water_prev, water_curr, water_photo, elec_prev, elec_curr, elec_photo, recorded_by, date)
billing:    BillingSettings(dormitory_fk, bill_day, grace_days, elec_rate, water_rate, tmr_api_key, tmr_secret, dunning_enabled)
            Bill(room_fk, month, base_rent, water_amt, elec_amt, total, due_date, status*)
            Payment(bill_fk, amount, tmr_ref, webhook_payload, idempotency_key, paid_at)
tenants:    TenantProfile(user_fk, room_fk, phone, line_id, id_card_no*)
            Lease(tenant_fk, start_date, end_date, document_file)
            DigitalVault(tenant_fk, file_type*, file)
maintenance:MaintenanceTicket(room_fk, reported_by, description, status*, technician)
            TicketPhoto(ticket_fk, photo, stage*)
            TicketStatusHistory(ticket_fk, status, changed_by, changed_at, note)
notify:     Parcel(room_fk, photo, carrier, notes, notified_at, logged_by)
            Broadcast(dormitory_fk, audience_type*, title, body, attachment, sent_at)
            DunningLog(bill_fk, trigger_type*, sent_at)

* Room.status:    occupied | vacant | cleaning | maintenance
* Bill.status:    draft | sent | paid | overdue
* file_type:      id_card | room_photo | contract
* TicketPhoto.stage: issue | completion
* Broadcast.audience_type: all | building | floor
* DunningLog.trigger_type: pre_7d | pre_3d | pre_1d | due | post_1d | post_7d | post_15d
* TenantProfile.id_card_no: encrypted at rest (PDPA)
```

---

## Critical Business Rules
1. **ห้ามข้าม tenant** — query ทุกอันต้อง filter ด้วย `tenant_id` ของ request user เสมอ
2. **Payment Idempotency** — ก่อน update bill status ต้อง check ว่า webhook นี้ถูก process ไปแล้วหรือยัง
3. **Billing cycle** — กำหนดต่อหอพัก, รองรับ pro-rate เมื่อผู้เช่าเข้า/ออกกลางเดือน
4. **Dunning schedule** — 7/3/1 วันก่อนครบ, วันครบกำหนด, +1/+7/+15 วันหลังค้าง
5. **Activity Log** — บันทึกทุก action สำคัญ (ใคร, ทำอะไร, เมื่อไหร่, tenant ใด)

---

## AI Team Configuration

| Agent | บทบาท | Model | ใช้เมื่อ |
|---|---|---|---|
| `@agent-md-orchestrator` | MD / หัวหน้าโปรเจกต์ | Opus | เริ่ม feature ใหม่, sprint planning, resolve conflict |
| `@agent-dev` | นักพัฒนา | Sonnet | Implement, แก้ bug, code review |
| `@agent-tester` | QA | Sonnet | ทดสอบ feature, regression test |
| `@agent-marketing` | การตลาด | Sonnet | Pitch ลูกค้า, เตรียม demo |
| `@agent-seo` | SEO/โปรโมท | Sonnet | Content, keyword, landing page |
| `@agent-customer-ca` | Persona (หอเล็ก) | Haiku | Simulate เจ้าของหอ < 50 ห้อง |
| `@agent-customer-cb` | Persona (หอกลาง) | Haiku | Simulate เจ้าของหอ 50–200 ห้อง |
| `@agent-customer-cc` | Persona (หอใหญ่) | Haiku | Simulate เจ้าของหอ 200+ ห้อง |

### Sub-Agent Routing

**Parallel dispatch (รันพร้อมกัน)**
- `@agent-customer-ca` + `@agent-customer-cb` + `@agent-customer-cc` — pitch session เสมอ
- Frontend task + Backend task ที่ไม่ depend กัน
- SEO content + Marketing deck สำหรับ launch

**Sequential dispatch (รันต่อกัน)**
```
Dev implement → Tester ตรวจ → ถ้า pass → MD approve
                             → ถ้า fail → Dev แก้ → Tester ยืนยันซ้ำ
```

---

## Team Agents (Specialized)

### `model-architect`
**รับผิดชอบ:** Django models, migrations, database schema
- ออกแบบ/แก้ไข models และ relationships
- เขียน migrations และ data migrations
- ตรวจสอบ tenant isolation ใน schema
- **ห้ามแตะ:** views, templates, business logic

### `billing-engine`
**รับผิดชอบ:** ระบบการเงินทั้งหมด
- `apps/billing/` — bill generation, payment status
- TMR Webhook handler + Idempotency logic
- Pro-rate calculation, billing cycle
- Export CSV report
- **ต้องเขียน test ทุกครั้งที่แก้ calculation**

### `line-integration`
**รับผิดชอบ:** LINE Messaging API (notifications เท่านั้น — ไม่มี LIFF)
- `apps/notifications/` — LINE Messaging API, push messages
- Dunning scheduler (Celery tasks)
- Digital receipt message format

### `frontend`
**รับผิดชอบ:** Django templates สำหรับ Owner/Staff
- `apps/*/templates/` — HTML, CSS, JS
- Django Unfold admin customization
- Owner Dashboard UI
- i18n: ทุก user-facing string ต้องใช้ `{% trans %}`
- **ห้ามแตะ:** models, views business logic

### `devops`
**รับผิดชอบ:** infrastructure และ environment
- `docker-compose.yml`, `Dockerfile`
- Environment variables, secrets management
- Redis, PostgreSQL configuration
- Local file storage setup

### `qa`
**รับผิดชอบ:** quality และ security
- เขียนและรัน tests (`pytest` / `django test`)
- ตรวจสอบ tenant isolation leak
- ตรวจสอบ SQL injection, XSS, IDOR
- Review billing calculation edge cases
- ตรวจสอบว่าทุก view มี authentication + permission check

---

## Workflow

### เพิ่ม Feature ใหม่
```
1. บอก MD requirement
2. MD วางแผน + แตก task
3. Dev implement
4. Tester ตรวจ
5. MD approve + deploy
```

### Pitch ลูกค้า
```
1. บอก Marketing ว่าจะ pitch feature อะไร
2. Marketing เตรียม pitch
3. Spawn CA + CB + CC (Agent Team)
4. Marketing present → ลูกค้า react
5. Marketing สรุป feedback → MD
6. MD สั่ง Dev ปรับปรุง
```

---

## UI / Frontend Best Practices

### Dark Mode
- Tailwind ใช้ `darkMode: 'class'` (อยู่ใน `base.html` และ `base_tenant.html`) — **ไม่ใช้ media strategy**
- `<html>` tag set class `dark` ตาม `request.user.theme` (`CustomUser.theme = 'light' | 'dark'`)
- Toggle ผ่าน `POST /core/theme/toggle/` — ปุ่มอยู่ใน header ทั้งสอง base templates
- **ทุก template ใหม่ต้องมี dark: variant คู่กับ light color เสมอ:**

| Light class | Dark pair ที่ต้องใส่ |
|---|---|
| `bg-white` | `dark:bg-slate-800` |
| `bg-slate-50` | `dark:bg-slate-700` |
| `bg-slate-100` | `dark:bg-slate-700` |
| `border-slate-100` | `dark:border-slate-700` |
| `border-slate-200` | `dark:border-slate-600` |

- ตรวจหา missing dark class ด้วย: `grep -rn 'bg-white\|bg-slate-50' templates/ | grep -v 'dark:bg-'`

### Card / Section Layout
- Section แต่ละ block ต้องเป็น card แยก: `bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-600 shadow-sm p-4`
- **ห้ามใช้ `border-y` แบบ full-width** ที่ชิดขอบจอ — ผู้ใช้มองดูไม่สวย

### Filter UI
- Status filter ใช้ `<select onchange="this.form.submit()">` — ไม่ใช้ pill chips หรือ tab underline
- List ที่มี filter วันที่ (เช่น Bills) ให้ default = เดือนปัจจุบัน (`now.strftime('%Y-%m')`)
- ปุ่ม "Clear" แสดงเฉพาะเมื่อ filter ต่างจาก default (`{% if status_filter or month_filter != default_month %}`)

---

## Out of Scope
- ระบบบัญชี/ภาษีเต็มรูปแบบ
- IoT / Hardware integration
- Multi-language UI (v1 — เตรียม i18n ไว้แต่ไม่ implement)
