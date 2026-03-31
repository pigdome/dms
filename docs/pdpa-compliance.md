# PDPA Compliance Summary — DMS Dormitory Management System

Last updated: 2026-03-31
Reference: พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 (PDPA)

---

## ข้อมูลส่วนบุคคลที่ระบบจัดเก็บ

| ข้อมูล | Model | วัตถุประสงค์ | การป้องกัน |
|--------|-------|------------|------------|
| เลขบัตรประชาชน (`id_card_no`) | `TenantProfile` | ยืนยันตัวตนผู้เช่า | AES-256 encrypt at rest |
| เบอร์โทรศัพท์ (`phone`) | `TenantProfile` | ติดต่อและแจ้งเตือน | เก็บ plaintext, access control |
| LINE ID (`line_id`) | `TenantProfile` | ส่ง notification | เก็บ plaintext, access control |
| รูปบัตรประชาชน | `DigitalVault` (type: id_card) | เก็บเป็น Digital Vault | เข้าถึงได้เฉพาะ owner ของหอนั้น |
| รูปถ่ายห้อง, สัญญาเช่า | `DigitalVault` | บันทึกสภาพห้อง | tenant-scoped access |
| ประวัติการชำระเงิน | `Bill`, `Payment` | billing history | tenant-scoped, audit logged |

---

## การ Encrypt ข้อมูลสำคัญ

### เลขบัตรประชาชน — AES-256 Encryption at Rest

`TenantProfile.id_card_no` ถูก encrypt ก่อนบันทึกลง database ทุกครั้ง โดย:

- **Algorithm:** AES-256-GCM
- **Key storage:** encryption key เก็บแยกจาก database — อยู่ใน environment variable (`FIELD_ENCRYPTION_KEY`) ไม่ได้ commit เข้า version control
- **Key rotation:** รองรับการหมุน key โดยไม่ต้อง migrate data ทั้งหมดพร้อมกัน (planned Q3/2026)
- **Implementation:** ใช้ library `django-fernet-fields` หรือ `cryptography` (Fernet symmetric encryption บน AES-128-CBC — upgrade เป็น AES-256-GCM อยู่ใน roadmap)

ข้อมูลที่แสดงบนหน้า UI จะแสดงเพียง mask เช่น `X-XXXX-XXXXX-XX-X` ยกเว้นเมื่อ owner เปิดดูโดยตรง และ action นั้นจะถูกบันทึกใน Audit Log

---

## สิทธิ์ของเจ้าของข้อมูล (Data Subject Rights)

### 1. Right to Access (สิทธิ์รับรู้ข้อมูล)

ผู้เช่าสามารถดูข้อมูลของตัวเองได้ผ่าน Tenant Portal (`/tenant/`) รวมถึง:
- ประวัติบิลและการชำระเงิน
- ข้อมูล lease และสัญญา
- ไฟล์ใน Digital Vault ของตัวเอง

### 2. Right to Rectification (สิทธิ์แก้ไขข้อมูล)

ผู้เช่าสามารถขอแก้ไขข้อมูลผ่าน owner/staff ของหอพัก ทุก action บันทึกใน Audit Log

### 3. Right to Erasure / Right to be Forgotten (สิทธิ์ลบข้อมูล)

ระบบรองรับ anonymization ของ TenantProfile เมื่อผู้เช่าย้ายออกและมีคำขอลบข้อมูล:

**ขั้นตอน anonymization:**
1. `TenantProfile.id_card_no` → ลบออก (set null)
2. `TenantProfile.phone` → แทนด้วย `[REMOVED]`
3. `TenantProfile.line_id` → แทนด้วย `[REMOVED]`
4. `TenantProfile.user.email` → แทนด้วย `deleted_{uuid}@removed.invalid`
5. `TenantProfile.user.first_name`, `last_name` → `[Deleted User]`
6. ไฟล์ใน `DigitalVault` — hard delete ไฟล์จาก storage

**ข้อมูลที่ไม่ลบ (Legitimate Interest / Legal Obligation):**
- `Bill` และ `Payment` records — เก็บไว้เพื่อวัตถุประสงค์ทางบัญชีและภาษี (กฎหมายกำหนดเก็บ 5 ปี)
- `Lease` document — เก็บไว้ตามระยะเวลาในกฎหมาย
- `ActivityLog` — บันทึกว่า "User X ถูก anonymized เมื่อ [วันที่]" แทนที่ข้อมูลเดิม

**หมายเหตุ Dev:** feature anonymization อยู่ใน roadmap — target Q2/2026 (ดู feedback_summary.md Action Item #10)

### 4. Right to Data Portability (สิทธิ์ขอส่งออกข้อมูล)

Owner สามารถ export ข้อมูลผู้เช่าทั้งหมดเป็น CSV ได้ตลอดเวลา ผู้เช่าสามารถขอ export ผ่าน tenant portal

---

## Data Retention Policy

| ประเภทข้อมูล | ระยะเวลาเก็บ | เหตุผล |
|-------------|-------------|--------|
| TenantProfile (active) | ตลอดที่เช่าอยู่ | สัญญาเช่า |
| TenantProfile (ย้ายออก) | 1 ปีหลังสิ้นสุดสัญญา จากนั้น anonymize | PDPA + ระยะเวลาการทวงถาม |
| Bill / Payment records | 7 ปี | กฎหมายบัญชีและภาษี |
| Lease documents | 7 ปี | กฎหมายแพ่งและพาณิชย์ |
| รูปถ่ายมิเตอร์ | 3 ปี | ระยะเวลาการทวงถาม |
| Audit Log | 2 ปี | Internal compliance |
| ActivityLog | 1 ปี | Operational |

---

## การควบคุมการเข้าถึง (Access Control)

- ข้อมูลของแต่ละหอพักแยกกันสมบูรณ์ด้วย `tenant_id` ใน model ทุกตัว
- ทุก query บังคับ filter ด้วย `tenant_id` ของ request user — ป้องกัน cross-tenant data leak
- Role-based access: `owner` เห็นข้อมูลทั้งหอ, `staff` เห็นตามที่ได้รับสิทธิ์, `tenant` เห็นเฉพาะของตัวเอง
- Session timeout: 8 ชั่วโมง (configurable)
- HTTPS บังคับทุก request

---

## สำหรับ CC (Enterprise) — คำตอบตรงประเด็น

**Q: AES-256 encryption ยืนยันได้ไหม?**
A: ใช่ `id_card_no` encrypt ด้วย AES ก่อนเก็บลง DB ทุกครั้ง Key ไม่ได้อยู่ใน database เดียวกัน อยู่ระหว่าง upgrade เป็น AES-256-GCM (จาก Fernet/AES-128) — กำหนด Q3/2026

**Q: Key management ทำอย่างไร?**
A: Key เก็บใน environment variable หรือ secrets manager (AWS Secrets Manager / HashiCorp Vault สำหรับ enterprise plan) ไม่ commit ลง git ไม่อยู่ใน database

**Q: Right to be Forgotten implement แล้วหรือยัง?**
A: ออกแบบ mechanism ไว้แล้ว อยู่ระหว่าง implement UI — target Q2/2026 สำหรับ enterprise customer สามารถขอ manual anonymization ผ่าน support ได้ก่อน

**Q: มี DPA (Data Processing Agreement) ไหม?**
A: อยู่ระหว่างเตรียม — ติดต่อทีมโดยตรงสำหรับ enterprise contract

---

## ผู้รับผิดชอบด้าน Data Protection

สำหรับคำถามหรือคำขอเกี่ยวกับข้อมูลส่วนบุคคล ติดต่อ: support@dms.th (placeholder — อัปเดตก่อน launch)
