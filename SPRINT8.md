# Sprint 8 — Priority 1 Task Breakdown

**Sprint period:** 2026-04-03 ~ 2026-04-17
**Status:** Planning

---

## S8-1: Custom 404/500 Pages

**Difficulty:** Easy (0.5 story point)
**Estimated time:** 30 minutes

### Current State Assessment

- `templates/404.html` และ `templates/500.html` มีอยู่แล้ว พร้อม dark mode support
- `config/urls.py` line 39-40 กำหนด handler แล้ว:
  ```python
  handler404 = 'apps.core.views.custom_404'
  handler500 = 'apps.core.views.custom_500'
  ```
- `apps/core/views.py` line 16-21 มี view functions แล้ว:
  ```python
  def custom_404(request, exception=None):
      return render(request, '404.html', status=404)

  def custom_500(request):
      return render(request, '500.html', status=500)
  ```
- **ปัญหา:** Django จะใช้ custom error pages เฉพาะเมื่อ `DEBUG=False` เท่านั้น
  - Production config ใช้ `DEBUG = config('DEBUG', default=False, cast=bool)` ซึ่งถูกต้อง

### Tasks

| # | Task | File | Line |
|---|------|------|------|
| 1 | Verify templates render สำเร็จเมื่อ `DEBUG=False` | `templates/404.html`, `templates/500.html` | - |
| 2 | ตรวจสอบว่า `bg-primary` class มี Tailwind config รองรับ (เพราะ 404/500 ใช้ CDN Tailwind แยกจาก base template) | `templates/404.html` line 14, `templates/500.html` line 14 | 14 |
| 3 | เขียน test: `GET /nonexistent-url/` returns 404 + correct template | `apps/core/tests.py` | new |

### Acceptance Criteria

- [ ] `GET /this-does-not-exist/` returns HTTP 404 with custom template (ไม่ใช่ Django default)
- [ ] `templates/500.html` renders ได้แม้ DB ล่ม (ห้ามมี DB query ใน template)
- [ ] Dark mode ทำงาน (มี `dark:` classes ครบ)
- [ ] Link "กลับหน้าหลัก" พาไปหน้า root `/` ได้

### Edge Cases

1. **500.html ต้อง self-contained** — ห้าม extend base template เพราะ base อาจ query DB (ซึ่ง DB อาจล่มอยู่) -- ปัจจุบันเป็น standalone HTML อยู่แล้ว ถูกต้อง
2. **CDN Tailwind ใน error pages** — ปัจจุบันใช้ `cdn.tailwindcss.com` ซึ่งถ้า CDN ล่มพร้อม server จะไม่มี styling -- ยอมรับได้สำหรับ v1
3. **`bg-primary` ไม่ใช่ Tailwind default class** -- ต้องตรวจว่าปุ่ม "กลับหน้าหลัก" แสดงสีถูกต้อง หรือต้องเปลี่ยนเป็น `bg-blue-600` / inline style

### Implementation Notes

**ส่วนใหญ่ทำเสร็จแล้ว** -- เหลือแค่:
1. แก้ `bg-primary` ให้เป็น Tailwind utility ที่มีอยู่จริง (เช่น `bg-blue-600`) หรือ inline style เพราะ CDN Tailwind ไม่รู้จัก custom `primary` color
2. เขียน test ยืนยัน

---

## S8-2: Password Change Self-Service (Tenant Portal)

**Difficulty:** Medium (2 story points)
**Estimated time:** 2-3 hours

### Current State Assessment

- `CustomUser.must_change_password` field มีแล้ว (migration 0006)
- `TenantChangePasswordView` ใน `apps/tenants/views.py` line 451-492 -- **implement เสร็จแล้ว**
- URL registered ใน `apps/tenants/tenant_urls.py` line 16: `path('change-password/', ...)`
- Template `templates/tenants/tenant_change_password.html` มีครบ พร้อม dark mode
- **ขาด:** Middleware force redirect เมื่อ `must_change_password=True`
  - ปัจจุบัน MIDDLEWARE ใน `config/settings.py` line 44-55 ไม่มี force password change middleware
  - Tenant สามารถ bypass ได้โดยไม่ไปหน้า change password

### Tasks

| # | Task | File | Line | Detail |
|---|------|------|------|--------|
| 1 | สร้าง `ForcePasswordChangeMiddleware` | `config/middleware.py` | new section | Intercept ทุก request ของ tenant ที่ `must_change_password=True` แล้ว redirect ไป `/tenant/change-password/` |
| 2 | Register middleware ใน `MIDDLEWARE` list | `config/settings.py` | 55 (หลัง `ActiveDormitoryMiddleware`) | เพิ่ม `'config.middleware.ForcePasswordChangeMiddleware'` |
| 3 | เขียน test: tenant ที่ `must_change_password=True` ถูก redirect | `apps/tenants/tests.py` | new |
| 4 | เขียน test: tenant ที่ `must_change_password=False` เข้าหน้าปกติได้ | `apps/tenants/tests.py` | new |
| 5 | เขียน test: เปลี่ยน password สำเร็จ -> `must_change_password` เป็น False -> redirect home | `apps/tenants/tests.py` | new |

### Acceptance Criteria

- [ ] Tenant ที่ `must_change_password=True` ถูก redirect ไป `/tenant/change-password/` ทุก URL
- [ ] หน้า change-password เอง ไม่ถูก redirect (ไม่งั้น infinite loop)
- [ ] Logout URL (`/logout/`) ไม่ถูก redirect (ต้อง logout ได้เสมอ)
- [ ] Static files / health check ไม่ถูก redirect
- [ ] หลังเปลี่ยน password สำเร็จ `must_change_password` = False และ redirect ไป `/tenant/home/`
- [ ] Session ยังคงอยู่หลังเปลี่ยน password (มี `update_session_auth_hash` อยู่แล้ว line 489)
- [ ] Owner/Staff/Superadmin ไม่ถูก affect โดย middleware นี้

### Edge Cases

1. **Infinite redirect loop** -- middleware ต้อง exempt `/tenant/change-password/`, `/logout/`, `/health/`, static/media paths
2. **Non-tenant roles** -- middleware ต้อง skip user ที่ไม่ใช่ tenant (owner ที่มี `must_change_password=True` ไม่ควรถูก redirect ไปหน้า tenant portal)
3. **AJAX/API requests** -- ถ้ามี fetch/XHR ควร return JSON error แทน redirect (พิจารณาสำหรับ v2)
4. **Password validation** -- ปัจจุบันเช็คเฉพาะ length >= 8 (line 480-481) -- เพียงพอสำหรับ v1

### Middleware Pseudocode

```python
class ForcePasswordChangeMiddleware:
    EXEMPT_PATHS = [
        '/tenant/change-password/',
        '/logout/',
        '/health/',
        '/static/',
        '/media/',
        '/admin/',
    ]

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.user.role == 'tenant' and request.user.must_change_password:
                if not any(request.path.startswith(p) for p in self.EXEMPT_PATHS):
                    return redirect('tenant:change_password')
        return self.get_response(request)
```

---

## S8-3: Invoice Number Sequence Retry / Collision Prevention

**Difficulty:** Medium (2 story points)
**Estimated time:** 2-3 hours

### Current State Assessment

`apps/billing/models.py` line 132-148 -- `Bill.save()`:

```python
def save(self, *args, **kwargs):
    if self.room_id and not getattr(self, 'dormitory_id', None):
        self.dormitory_id = self.room.dormitory_id

    if not self.invoice_number and self.room_id:
        dorm = self.dormitory or self.room.floor.building.dormitory
        prefix = dorm.invoice_prefix or 'INV'
        ym = self.month.strftime('%y%m')
        with transaction.atomic():
            seq = (
                Bill.unscoped_objects.select_for_update()
                .filter(room__floor__building__dormitory=dorm, month=self.month)
                .exclude(pk=self.pk)
                .count()
            ) + 1
            self.invoice_number = f'{prefix}-{ym}-{seq:03d}'
    super().save(*args, **kwargs)
```

### Problems Identified

1. **Race condition ยังเป็นไปได้:** `select_for_update()` lock rows ที่มีอยู่ แต่ถ้า 2 requests เข้ามาพร้อมกันและ count เท่ากัน จะได้ invoice_number ซ้ำ -> `IntegrityError` (unique constraint)
2. **`super().save()` อยู่นอก `transaction.atomic()` block:** ถ้า save ล้มเหลว, transaction ก่อนหน้าจะ commit ไปแล้ว ทำให้ lock หลุด
3. **ไม่มี retry logic:** เมื่อเกิด `IntegrityError` จะ raise ขึ้นไปตรง ๆ ไม่มี recovery
4. **seq format `{seq:03d}` จำกัดที่ 999:** ถ้าหอใหญ่มี > 999 bills/month จะเกิน format (แต่ไม่น่าเกิดจริง)

### Tasks

| # | Task | File | Line | Detail |
|---|------|------|------|--------|
| 1 | ย้าย `super().save()` เข้าไปใน `transaction.atomic()` block | `apps/billing/models.py` | 140-148 | ป้องกัน lock หลุดก่อน save |
| 2 | เพิ่ม retry loop (max 3 attempts) เมื่อเกิด `IntegrityError` | `apps/billing/models.py` | 136-148 | ถ้า collision ให้ re-count + retry |
| 3 | เปลี่ยน seq logic จาก count-based เป็น MAX-based | `apps/billing/models.py` | 141-146 | ใช้ `Max` + parse existing invoice numbers หรือเก็บ seq field แยก เพราะ count อาจไม่ตรงถ้ามี bill ถูกลบ |
| 4 | เขียน test: concurrent bill creation ไม่เกิด collision | `apps/billing/tests.py` | new |
| 5 | เขียน test: bill ถูกลบแล้วสร้างใหม่ -> seq ไม่ซ้ำ | `apps/billing/tests.py` | new |

### Acceptance Criteria

- [ ] สร้าง Bill 2 ใบพร้อมกัน (concurrent) ไม่เกิด `IntegrityError`
- [ ] Invoice number ไม่ซ้ำกันเด็ดขาด (unique constraint enforced)
- [ ] ถ้ามี bill ถูกลบไปแล้ว seq ไม่กลับไปใช้เลขเดิม
- [ ] Retry ไม่เกิน 3 ครั้ง ถ้ายังชนก็ raise error ให้จัดการ

### Edge Cases

1. **Deleted bills create seq gaps** -- count-based logic จะ re-use เลขที่ถูกลบ ต้องเปลี่ยนเป็น MAX-based
2. **Month rollover** -- seq reset ทุกเดือน ตาม `ym` -- ถูกต้องแล้ว
3. **Multi-dormitory** -- seq แยกตาม dormitory + month -- ถูกต้องแล้ว
4. **Dormitory ไม่มี `invoice_prefix`** -- fallback เป็น `'INV'` -- ถูกต้อง
5. **`select_for_update` + `transaction.atomic`** -- ต้อง wrap ทั้ง count + save ใน atomic block เดียวกัน

### Recommended Implementation

```python
def save(self, *args, **kwargs):
    if self.room_id and not getattr(self, 'dormitory_id', None):
        self.dormitory_id = self.room.dormitory_id

    if not self.invoice_number and self.room_id:
        from django.db import IntegrityError
        dorm = self.dormitory or self.room.floor.building.dormitory
        prefix = dorm.invoice_prefix or 'INV'
        ym = self.month.strftime('%y%m')
        pattern = f'{prefix}-{ym}-'

        for attempt in range(3):
            try:
                with transaction.atomic():
                    # MAX-based: หาเลขล่าสุดจาก invoice_number ที่ขึ้นต้นด้วย pattern
                    existing = (
                        Bill.unscoped_objects.select_for_update()
                        .filter(
                            room__floor__building__dormitory=dorm,
                            month=self.month,
                            invoice_number__startswith=pattern,
                        )
                        .exclude(pk=self.pk)
                        .order_by('-invoice_number')
                        .values_list('invoice_number', flat=True)
                        .first()
                    )
                    if existing:
                        last_seq = int(existing.split('-')[-1])
                    else:
                        last_seq = 0
                    seq = last_seq + 1
                    self.invoice_number = f'{prefix}-{ym}-{seq:04d}'
                    super().save(*args, **kwargs)
                return  # success
            except IntegrityError:
                self.invoice_number = None  # reset for retry
                if attempt == 2:
                    raise
    else:
        super().save(*args, **kwargs)
```

### Breaking Change Warning

- เปลี่ยนจาก `{seq:03d}` (3 หลัก) เป็น `{seq:04d}` (4 หลัก) จะทำให้ invoice number format เปลี่ยน
- **Recommendation:** คงไว้ `{seq:03d}` เพื่อ backward compatibility ยกเว้น owner ต้องการ

---

## S8-4: Dashboard Query Optimization + Caching

**Difficulty:** Easy-Medium (1.5 story points)
**Estimated time:** 1-2 hours

### Current State Assessment

`apps/dashboard/views.py` -- `DashboardView.get()` (line 12-94):

**Queries ปัจจุบัน (6 queries total):**

| # | Query | Line | N+1? | Optimized? |
|---|-------|------|------|------------|
| 1 | `Bill.objects.filter(...).aggregate(total_income, last_month_income, overdue_amount)` | 38-52 | No | Yes (single aggregate) |
| 2 | `Bill.objects.filter(...overdue).values('room').distinct().count()` | 64-67 | No | OK |
| 3 | `rooms_qs.filter(status='vacant').count()` | 70 | No | OK |
| 4 | `MaintenanceTicket.objects.filter(...).count()` | 73-76 | No | OK |
| 5 | `ActivityLog.objects.filter(...).select_related('user')[:10]` | 79-81 | No | Yes (select_related) |
| 6 | Dormitory lookup (implicit) | 14 | No | OK |

**Assessment:** Dashboard queries ถูก optimize ไว้แล้วในระดับดี
- ไม่มี N+1 problem
- ใช้ conditional aggregation (query 1)
- ใช้ `select_related` (query 5)

### Optimization Opportunities

1. **Merge queries 2-4 เข้าด้วยกัน** -- ใช้ subquery annotation บน rooms_qs เพื่อลดจาก 3 queries เหลือ 1
2. **Cache dashboard stats** -- ใช้ Redis cache (มี config แล้ว) cache ผลลัพธ์ 5-10 นาที
3. **ReportView** (line 97-171) ใช้ single annotated query อยู่แล้ว -- ดีอยู่แล้ว

### Tasks

| # | Task | File | Line | Detail |
|---|------|------|------|--------|
| 1 | Merge overdue_count + vacant_count + pending_maintenance เป็น single query | `apps/dashboard/views.py` | 64-76 | ใช้ `Subquery` หรือ raw annotate |
| 2 | เพิ่ม cache layer สำหรับ dashboard stats (TTL 5 นาที) | `apps/dashboard/views.py` | 27-92 | ใช้ `django.core.cache` + cache key per dormitory |
| 3 | Cache invalidation เมื่อ bill status เปลี่ยน | `apps/billing/models.py` | post_save signal or save() | ลบ cache key ของ dormitory ที่เกี่ยวข้อง |
| 4 | เขียน test: cache hit/miss behavior | `apps/dashboard/tests.py` | new |

### Acceptance Criteria

- [ ] Dashboard load time ลดลง (วัดด้วย Django Debug Toolbar หรือ response time)
- [ ] Cache invalidate อัตโนมัติเมื่อมี bill/payment/room status เปลี่ยน
- [ ] Cache key แยกตาม dormitory (tenant isolation)
- [ ] ไม่มี stale data นานเกิน 5 นาที

### Edge Cases

1. **Cache key ต้อง include dormitory_id** -- ป้องกัน tenant data leak ผ่าน cache
2. **Cache invalidation race** -- ถ้า invalidate พร้อม read อาจได้ stale data ชั่วคราว (ยอมรับได้)
3. **Redis ล่ม** -- ต้อง fallback ไป query ปกติ (django cache framework ทำให้อัตโนมัติ)
4. **Multi-dormitory owner** -- cache key ต้องตาม active dormitory ไม่ใช่ user

### Recommended Cache Implementation

```python
from django.core.cache import cache

def _dashboard_cache_key(dormitory_id):
    return f'dashboard:stats:{dormitory_id}'

# In DashboardView.get():
cache_key = _dashboard_cache_key(dorm.pk)
stats = cache.get(cache_key)
if stats is None:
    # ... run queries ...
    stats = { ... }
    cache.set(cache_key, stats, timeout=300)  # 5 min

# Invalidation (in billing/signals.py or Bill.save):
cache.delete(_dashboard_cache_key(bill.dormitory_id))
```

---

## Implementation Order (Recommended)

| Order | Item | Reason |
|-------|------|--------|
| 1 | **S8-1** Custom 404/500 | Easy, quick win, no dependencies |
| 2 | **S8-2** Password change force redirect | Security-critical, middleware needed |
| 3 | **S8-3** Invoice number collision | Data integrity, affects billing |
| 4 | **S8-4** Dashboard caching | Performance improvement, least urgent |

---

## Summary

| Item | Difficulty | Est. Hours | Status |
|------|-----------|------------|--------|
| S8-1 Custom 404/500 | Easy | 0.5h | Code exists, needs verification + fix `bg-primary` |
| S8-2 Password change | Medium | 2-3h | View/template done, **needs middleware** |
| S8-3 Invoice collision | Medium | 2-3h | Needs rewrite of `Bill.save()` seq logic |
| S8-4 Dashboard cache | Easy-Medium | 1-2h | Queries already optimized, add cache layer |
| **Total** | | **6-8.5h** | |
