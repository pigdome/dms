# Sprint 7 Plan — Production Readiness + New Features

วางแผน: 2026-04-02 | สถานะ: COMPLETED (ยืนยัน 2026-04-03)

---

## Phase 0: Production Blockers (ต้องแก้ก่อน deploy ทุกอย่าง)

### B1. Webhook Race Condition (Payment) 🔴 BLOCKER
- **File:** `apps/billing/views.py` line ~183-191
- **ปัญหา:** `select_for_update()` อยู่ **นอก** `atomic()` block → concurrent webhooks ผ่าน idempotency check พร้อมกันได้ → duplicate payment
- **Fix:** ย้าย `select_for_update()` ให้อยู่ใน `atomic()` block เดียวกัน

### B2. TMR Webhook Signature Bypass 🔴 BLOCKER
- **File:** `apps/billing/views.py` line ~159-164
- **ปัญหา:** `if secret:` — ถ้า `TMR_WEBHOOK_SECRET` ว่าง (default ใน .env.example) จะข้าม HMAC verify ทั้งหมด → ใครก็ POST มาได้เพื่อมาร์คบิลว่าจ่ายแล้ว
- **Fix:** ถ้าไม่มี secret ให้ reject request ทันที (return 400/403)

### B3. TMR API Key Leaked ไปหา Tenant 🔴 BLOCKER
- **File:** `apps/tenants/views.py` line ~339-340
- **ปัญหา:** `tmr_qr_url = f"https://payment.tmr.th/qr/{billing_settings.tmr_api_key}/..."` — API key โผล่ใน URL ที่ tenant เห็นได้
- **Fix:** Generate QR server-side หรือใช้ public merchant ID แทน secret API key

### B4. Django Security Settings ขาดหมด 🔴 BLOCKER
- **File:** `config/settings.py`
- **ปัญหา:** ไม่มี `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF`
- **Fix:** เพิ่ม security settings ทั้งหมด toggle ด้วย env var

### B5. Media Files 404 ใน Production 🔴 BLOCKER
- **File:** `config/urls.py` line ~81-82
- **ปัญหา:** `if settings.DEBUG: urlpatterns += static(...)` — ปิด DEBUG แล้วรูปมิเตอร์/พัสดุ/บัตรประชาชน/สัญญา → 404 ทั้งหมด
- **Fix:** เพิ่ม Nginx config ใน docker-compose สำหรับ serve media files

### B6. Docker Production Config ไม่มี 🔴 BLOCKER
- **File:** `docker-compose.yml`
- **ปัญหา:** ไม่มี `restart: unless-stopped`, ไม่มี `healthcheck`, มี `--reload` ใน gunicorn, mount source code (`- .:/app`), ไม่ได้รัน `collectstatic`
- **Fix:** สร้าง `docker-compose.prod.yml` + เพิ่ม Nginx service + fix Dockerfile

### B7. ไม่มี Logging และ Error Tracking 🔴 BLOCKER
- **File:** `config/settings.py`
- **ปัญหา:** ไม่มี `LOGGING` config, ไม่มี Sentry → production error เงียบหมด
- **Fix:** เพิ่ม `LOGGING` dict + integrate `sentry-sdk`

### B8. ไม่มี Health Check Endpoint 🔴 BLOCKER
- **ปัญหา:** Container orchestrator ไม่รู้ว่า app พร้อมหรือเปล่า
- **Fix:** เพิ่ม `/health/` endpoint ใน `core/urls.py`

---

## Phase 1: Important Issues (แก้ใน Sprint นี้)

### I1. id_card_no Encryption at Rest (PDPA) 🟡
- **ปัญหา:** `TenantProfile.id_card_no` เป็น `CharField` ธรรมดา — ยังไม่ encrypt จริง
- **Solution:**
  - ใช้ `django-encrypted-model-fields` (AES-256)
  - เพิ่ม `id_card_hash` (HMAC-SHA256) สำหรับ exact-match query
  - Masking display: `X-XXXX-XXXXX-XX-X` แสดงแค่ 4 ตัวท้าย
  - Data migration encrypt ข้อมูลเดิม
- **ตอบคำถาม: ใช้งานหลัง encrypt ยังไง?**
  | Use case | วิธี |
  |---|---|
  | แสดงผล | decrypt on authorized read (Owner/Staff) |
  | ค้นหา/verify | ใช้ `id_card_hash` (HMAC) |
  | Masking | แสดง `X-XXXX-XXXXX-XX-X` ให้ user ทั่วไป |

### I2. Staff Permission Granularity 🟡
- **ปัญหา:** Staff มีสิทธิ์เหมือนกัน ไม่สามารถแยกย่อยได้
- **Solution:** สร้าง `StaffPermission` model + UI checkbox matrix
- **Permission flags:** `can_view_billing`, `can_record_meter`, `can_manage_maintenance`, `can_log_parcels`, `can_view_tenants`

### I3. Pro-rated Rent ไม่ถูก Apply ใน Bill Generation 🟡
- **File:** `apps/billing/services.py` line ~98
- **ปัญหา:** `generate_bills_for_dormitory()` ใช้ `room.base_rent` ตรงๆ เสมอ — ฟังก์ชัน `calculate_prorated_rent()` มีอยู่แล้วแต่ไม่ถูกเรียก
- **Fix:** เรียก `calculate_prorated_rent()` เมื่อ lease start date อยู่ในเดือนปัจจุบัน

### I4. Webhook Amount Validation 🟡
- **File:** `apps/billing/views.py` line ~194
- **ปัญหา:** `amount=data.get('amount', bill.total)` — ไม่มีการตรวจว่าจำนวนเงินตรงกับ bill หรือเปล่า
- **Fix:** validate amount และ log warning ถ้าไม่ตรง

### I5. Default Password = Username 🟡
- **File:** `apps/tenants/views.py` line ~118, `apps/core/views.py` line ~873
- **ปัญหา:** Import tenant → password ถูก set เป็น username → ไม่ปลอดภัย
- **Fix:** Force password change on first login หรือ generate random password + ส่งผ่าน LINE

### I6. Database Indexes 🟡
- **ปัญหา:** ขาด index บน field ที่ query บ่อย
- **Fields ที่ต้องเพิ่ม:** `Bill.status`, `Bill.month`, `Bill.due_date`, `Room.status`, `Lease.status`, `Lease.end_date`, `TenantProfile.is_deleted`

### I7. Celery Task Retry Config ไม่ครบ 🟡
- **File:** `apps/notifications/tasks.py` lines ~269, ~381
- **ปัญหา:** `check_lease_expiry_task` และ `pdpa_auto_purge_task` ไม่มี retry config
- **Fix:** เพิ่ม `bind=True, max_retries=3` เหมือน tasks อื่น

### I8. Tests ใช้ SQLite แทน PostgreSQL 🟡
- **File:** `config/settings.py` lines ~88-92
- **ปัญหา:** `select_for_update`, UUID fields, JSON queries ทำงานต่างกัน → bug B1 จะไม่โดน catch
- **Fix:** ใช้ PostgreSQL test DB (หรือ `pytest-django` + `--reuse-db`)

### I9. Broadcast Preview 🟡
- **ปัญหา:** กด Send แล้วส่งทันที ไม่มี preview
- **Fix:** เพิ่ม step Preview ก่อน Confirm

---

## Phase 2: Nice-to-Have (defer ได้)

| # | Issue |
|---|---|
| N1 | OCR สแกนบัตรประชาชน (GLM-OCR) — ต้อง assess library ก่อน |
| N2 | Custom 404/500 error pages |
| N3 | Password change self-service ใน tenant portal |
| N4 | Invoice number sequence — retry logic กันชนกัน |
| N5 | Dashboard query optimization / caching |
| N6 | Broadcast preview LINE message format |

---

## Sprint 7 Execution Order

```
Phase 0 — Blockers (แก้ก่อน deploy):
  B1 Webhook race condition     (0.5 วัน)
  B2 Webhook signature bypass   (0.5 วัน)
  B3 TMR API key leak           (1 วัน)
  B4 Django security settings   (0.5 วัน)
  B5 Media files production     (1 วัน)
  B6 Docker prod config         (1 วัน)
  B7 Logging + Sentry           (0.5 วัน)
  B8 Health check endpoint      (0.5 วัน)
                        ──────────────────
                        รวม ~6 วัน

Phase 1 — Important:
  I1 id_card encryption         (1.5 วัน)
  I2 Staff permissions          (2 วัน)
  I3 Pro-rate fix               (0.5 วัน)
  I4 Webhook amount validation  (0.5 วัน)
  I5 Default password fix       (0.5 วัน)
  I6 DB indexes                 (0.5 วัน)
  I7 Celery retry fix           (0.5 วัน)
  I8 Test DB fix                (0.5 วัน)
  I9 Broadcast preview          (1 วัน)
                        ──────────────────
                        รวม ~7.5 วัน

Phase 2 — Defer to Sprint 8:
  N1 OCR (GLM-OCR)
  N2-N6 ตามลำดับ
```

**ประมาณเวลา Sprint 7: ~2 สัปดาห์** (dev 1 คน)

---

## Sprint 7 Final Status (ยืนยัน 2026-04-03)

### Phase 0 — Blockers: ALL DONE
| # | Item | Status |
|---|---|---|
| B1 | Webhook race condition (select_for_update in atomic) | DONE |
| B2 | Webhook signature bypass (reject empty secret 400) | DONE |
| B3 | TMR API key leak (server-side proxy) | DONE |
| B4 | Django security settings | DONE |
| B5 | Media files production (nginx config) | DONE |
| B6 | Docker prod config (docker-compose.prod.yml) | DONE |
| B7 | Logging + Sentry | DONE |
| B8 | Health check endpoint | DONE |

### Phase 1 — Important: ALL DONE
| # | Item | Status | หลักฐาน |
|---|---|---|---|
| I1 | id_card encryption (PDPA) | DONE | migration 0003_idcard_encryption.py |
| I2 | Staff permissions | DONE | StaffPermission model + views + tests |
| I3 | Pro-rate fix | DONE | `generate_bills_for_dormitory()` เรียก `calculate_prorated_rent()` เมื่อ lease start อยู่ในเดือนที่ generate |
| I4 | Webhook amount validation | DONE | log warning + mismatch detection |
| I5 | Default password fix | DONE | must_change_password field + migration 0006 |
| I6 | DB indexes | DONE | migrations 0004_add_indexes |
| I7 | Celery retry fix | DONE | `check_lease_expiry_task` และ `pdpa_auto_purge_task` มี `bind=True, max_retries=3, default_retry_delay=60` ครบ |
| I8 | Test DB PostgreSQL | DONE | 362 tests ผ่าน PostgreSQL |
| I9 | Broadcast preview | DONE | templates/notifications/broadcast_preview.html |

### Test Results
- Unit tests: 362/362 PASS
- E2E tests: 78/78 PASS

### สรุป: Sprint 7 COMPLETED -- ทุก item ใน Phase 0 + Phase 1 เสร็จสมบูรณ์
