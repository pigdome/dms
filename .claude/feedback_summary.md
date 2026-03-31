# Pitch Session Feedback Summary
Date: 2026-03-30
Session: DMS — Dormitory Management System
Conducted by: Marketing Agent

---

## FEEDBACK SUMMARY

### Feature: บิลอัตโนมัติ + QR PromptPay

CA: ตรงจุด ใช้งานได้ทันที — ชอบ
CB: Smart Billing ครอบคลุมความต้องการ — ชอบ
CC: Pro-rate calculation รองรับ enterprise ได้ — ชอบ

Action Items สำหรับ Dev:
- ไม่มี — feature นี้ได้รับการตอบรับดีจากทุกกลุ่ม

---

### Feature: Dunning LINE อัตโนมัติ

CA: แก้ปัญหาบิลค้างได้จริง — ชอบ
CB: Dunning LINE ครบ แต่อยากได้ช่องทาง SMS เพิ่ม — ต้องการเพิ่ม
CC: Dunning 7 ขั้นอัตโนมัติตรงกับ process — ชอบ

Action Items สำหรับ Dev:
- เพิ่ม SMS notification channel (CB requirement)

---

### Feature: Dashboard รวมหลายตึก

CA: ไม่ได้ใช้เยอะ (1 ตึก) — neutral
CB: เห็นทุกตึกหน้าเดียว ตรงปัญหา — ชอบ
CC: ต้องการ dashboard ที่ drill-down ได้ถึง room level — ต้องการเพิ่ม

Action Items สำหรับ Dev:
- ไม่มีเพิ่มเติม (existing feature ตอบโจทย์ CB แล้ว)

---

### Feature: Role-based Permission

CA: ไม่ค่อยจำเป็น (จัดการคนเดียว) — neutral
CB: ต้องการ lock permission จริงในระดับ backend ไม่ใช่แค่ซ่อน UI — ต้องการเพิ่ม
CC: ต้องการ Role Hierarchy 3 ชั้น: Owner → Building Manager → Staff — critical missing

Action Items สำหรับ Dev:
- enforce permission ใน backend (view-level + queryset-level) ไม่ใช่แค่ template logic
- ออกแบบ Role Hierarchy: Owner → Building Manager → Staff

---

### Feature: Audit Log

CA: ไม่ได้กล่าวถึง — neutral
CB: ไม่ได้กล่าวถึง — neutral
CC: ต้องการ log ว่าใครแก้อะไร เมื่อไหร่ พร้อม old value → new value — critical missing / ถ้าไม่มี = ไม่ซื้อ

Action Items สำหรับ Dev:
- implement Audit Log เก็บ actor, action, timestamp, old_value, new_value, model, record_id

---

### Feature: Export CSV / Report

CA: ไม่ได้กล่าวถึง — neutral
CB: ต้องการ report แยกตึก: รายได้, อัตราเข้าพัก %, บิลค้างชำระ — ต้องการเพิ่ม
CC: ต้องการ export CSV multi-month range พร้อม column มาตรฐาน — critical missing / ถ้าไม่มี = ไม่ซื้อ

Action Items สำหรับ Dev:
- สร้าง report view แยกตึก (รายได้, occupancy %, outstanding bills)
- export CSV รองรับ date range หลายเดือน พร้อม column มาตรฐาน

---

### Feature: Data Migration / Import Wizard

CA: ไม่ได้กล่าวถึง — neutral
CB: ต้องการ migrate ข้อมูลจาก Excel 3 ปี — ต้องการเพิ่ม
CC: ต้องการ Data Import Wizard (upload Excel room/tenant list) — ต้องการเพิ่ม

Action Items สำหรับ Dev:
- สร้าง Data Import Wizard รองรับ Excel upload สำหรับ room list และ tenant list
- รองรับ historical billing data migration

---

### Feature: PDPA / Security

CA: กังวลว่าข้อมูลเก็บที่ไหน — ต้องการเพิ่มข้อมูล
CB: ไม่ได้กล่าวถึง — neutral
CC: ต้องการ PDPA detail: AES-256 encryption, key management, right to be forgotten — ต้องการเพิ่ม

Action Items สำหรับ Dev:
- document และ implement AES-256 สำหรับ sensitive fields (id_card_no ทำแล้ว ต้องยืนยัน)
- implement "Right to be Forgotten" — soft delete + data purge mechanism
- เตรียม hosting info page: ระบุว่า host บน cloud ไทยหรือ on-premise option

---

### Feature: API Integration

CA: ไม่ได้กล่าวถึง — neutral
CB: ไม่ได้กล่าวถึง — neutral
CC: ต้องการ REST API สำหรับ integrate กับระบบบัญชีภายนอก — ต้องการเพิ่ม

Action Items สำหรับ Dev:
- ออกแบบ REST API layer (Django REST Framework) สำหรับ billing data export

---

## PRIORITIZED ACTION ITEMS FOR DEV

### High Priority — ทุกกลุ่มหรือ deal-breaker สำหรับ CC

| # | Feature | เหตุผล |
|---|---------|--------|
| 1 | Audit Log (actor, action, old→new value, timestamp) | CC: ถ้าไม่มี = ไม่ซื้อ — ระบบมี ActivityLog แต่ต้องเพิ่ม old/new value tracking |
| 2 | Export CSV multi-month range + standard columns | CC: ถ้าไม่มี = ไม่ซื้อ |
| 3 | Backend permission enforcement (ไม่ใช่แค่ hide UI) | CB + CC: security requirement จริง ต้องทำใน view/queryset level |

### Medium Priority — CB และ CC ต้องการ

| # | Feature | กลุ่ม |
|---|---------|-------|
| 4 | Role Hierarchy: Owner → Building Manager → Staff | CB + CC |
| 5 | Report แยกตึก: รายได้, occupancy %, บิลค้างชำระ | CB + CC |
| 6 | Data Import Wizard (Excel upload: room + tenant list) | CB + CC |
| 7 | SMS Notification channel (นอกจาก LINE) | CB |
| 8 | Maintenance Ticket → LINE notification ช่าง | CB |

### Enterprise Priority — CC เท่านั้น (Budget 15,000-20,000 บาท/เดือน)

| # | Feature | หมายเหตุ |
|---|---------|---------|
| 9 | REST API สำหรับ integrate ระบบบัญชีภายนอก | DRF layer |
| 10 | Right to be Forgotten (PDPA compliance) | soft delete + purge |
| 11 | AES-256 key management documentation | ยืนยัน spec ที่มีอยู่ |
| 12 | Mobile App สำหรับ Staff | CB ก็ต้องการ — อาจ upgrade priority |

---

## คำถามที่ต้องตอบก่อน Close Deal

### CA — Budget < 500 บาท/เดือน
- [ ] **ราคา:** plan สำหรับหอ < 10 ห้อง เท่าไหร่?
- [ ] **Hardware:** ต้องซื้ออุปกรณ์เพิ่มไหม?
- [ ] **Hosting:** เก็บข้อมูลบน cloud ไทยหรือ on-premise option มีไหม?
- [ ] **Non-LINE users:** ผู้เช่าที่ไม่มี LINE ใช้ tenant portal ผ่านช่องทางไหน?
- [ ] **Setup time:** Setup Wizard ใช้เวลากี่นาทีจริงๆ?

### CB — 3 ตึก 120 ห้อง
- [ ] **ราคา:** plan สำหรับ 3 ตึก / 120 ห้อง เท่าไหร่?
- [ ] **Permission detail:** staff lock ระดับ building ทำได้จริงหรือยัง?
- [ ] **Migration support:** ทีม support ช่วย migrate Excel 3 ปีได้ไหม? มี cost เพิ่มไหม?
- [ ] **Maintenance + LINE ช่าง:** เชื่อม ticket กับ LINE ช่างได้ไหม?

### CC — 7 ตึก 300 ห้อง (Budget 15,000-20,000 บาท/เดือน)
- [ ] **SLA:** มี 99.9% uptime SLA และ dedicated support ไหม?
- [ ] **Audit Log timeline:** implement ได้เมื่อไหร่?
- [ ] **Reference customers:** มี reference ลูกค้าหอใหญ่ให้ contact ได้ไหม?
- [ ] **Demo data:** จัด demo ด้วยข้อมูลจริง (anonymized) ได้ไหม?

---

## Conversion Likelihood

| กลุ่ม | ความพร้อมซื้อ | Blocker หลัก |
|-------|-------------|-------------|
| CA | 80% | ราคา + hosting info |
| CB | 80% | Permission detail + migration plan |
| CC | 60% | Audit Log + SLA (must-have ก่อน sign) |
