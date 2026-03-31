# Pricing Guide — DMS Dormitory Management System

Last updated: 2026-03-31
ราคาทุกแพลนยังไม่รวม VAT 7%

---

## ภาพรวม 3 แพลน

| | CA Starter | CB Professional | CC Enterprise |
|--|-----------|----------------|---------------|
| ขนาดหอพัก | ไม่เกิน 20 ห้อง | 21–200 ห้อง | 200+ ห้อง |
| ราคา/เดือน | **390 บาท** | **1,490 บาท** | **ติดต่อทีม** |
| ราคา/ปี (จ่ายล่วงหน้า) | 3,900 บาท (ประหยัด 16%) | 14,900 บาท (ประหยัด 17%) | ตามสัญญา |

---

## CA Starter — หอพักขนาดเล็ก ไม่เกิน 20 ห้อง

**390 บาท/เดือน**

เหมาะสำหรับ: เจ้าของหอพักรายเดี่ยว จัดการเองคนเดียว

### รวมทุกอย่างที่จำเป็น:
- ห้องพักสูงสุด 20 ห้อง (1 ตึก)
- บิลอัตโนมัติ + QR PromptPay
- จดมิเตอร์ไฟ-น้ำ พร้อมรูปถ่าย
- Dunning LINE อัตโนมัติ (แจ้งบิลค้าง 7 ขั้น)
- Tenant Portal สำหรับผู้เช่าดูบิลและจ่ายเงิน
- Maintenance Ticket
- บันทึกพัสดุ (Parcel Log)
- Digital Vault เก็บเอกสารผู้เช่า
- Dashboard สรุปรายได้
- Export CSV รายเดือน
- User 2 คน (owner + staff 1 คน)
- Support ผ่าน LINE OA (response ภายใน 1 วันทำการ)
- Cloud hosting บน cloud ไทย — ไม่ต้องซื้อ hardware เพิ่ม

### ไม่รวม:
- Multi-building management
- Report แยกตึก
- Role hierarchy

### คำถามที่ CA มักถาม:
- **ต้องซื้ออุปกรณ์เพิ่มไหม?** ไม่ต้อง ใช้มือถือที่มีอยู่ได้เลย
- **Setup นานไหม?** Setup Wizard ใช้เวลา 15–30 นาที
- **ถ้าหอโตเกิน 20 ห้อง?** upgrade เป็น CB ได้ทันที pro-rate ตามวันที่เหลือ

---

## CB Professional — หอพักขนาดกลาง 21–200 ห้อง

**1,490 บาท/เดือน**

เหมาะสำหรับ: หอพัก 2–5 ตึก ต้องการเห็น overview และจัดการ staff หลายคน

### รวมทุกอย่างใน CA Starter บวก:
- ห้องพักสูงสุด 200 ห้อง (หลายตึก)
- Multi-building Dashboard — เห็นทุกตึกในหน้าเดียว
- Report แยกตึก: รายได้, อัตราเข้าพัก %, บิลค้างชำระ
- Export CSV หลายเดือน (date range)
- Role-based permission: Owner + Staff (lock per building)
- User สูงสุด 10 คน
- Data Import Wizard (upload Excel room list + tenant list)
- SMS Notification (นอกจาก LINE)
- Maintenance Ticket → แจ้ง LINE ช่าง
- Support ผ่าน LINE OA (response ภายใน 4 ชั่วโมงวันทำการ)
- Onboarding session 1 ครั้ง (video call 1 ชั่วโมง)

### คำถามที่ CB มักถาม:
- **Permission lock ระดับ building ทำได้จริงไหม?** ได้ staff คนหนึ่งเห็นได้เฉพาะตึกที่ assign
- **Migration Excel 3 ปี ช่วยได้ไหม?** Import Wizard รองรับ Excel standard format — ถ้าต้องการ custom migration มี service fee เพิ่ม (ติดต่อทีม)
- **Maintenance กับ LINE ช่าง?** รองรับ — ช่างต้องมี LINE account

---

## CC Enterprise — หอพักขนาดใหญ่ 200+ ห้อง

**ราคาเริ่มต้น 15,000 บาท/เดือน** (ขึ้นอยู่กับจำนวนห้องและ feature ที่ต้องการ)

เหมาะสำหรับ: หอพักระดับ enterprise 5–20 ตึก ต้องการ data, compliance, SLA

### รวมทุกอย่างใน CB Professional บวก:
- ห้องพักไม่จำกัด
- ตึกไม่จำกัด
- Role Hierarchy 3 ชั้น: Owner → Building Manager → Staff
- Audit Log ครบ: actor, action, timestamp, old value → new value (ทุก model)
- Dashboard drill-down ถึงระดับ room
- REST API สำหรับ integrate ระบบบัญชีภายนอก (DRF)
- PDPA: Right to be Forgotten (anonymize tenant data)
- AES-256 key management documentation + key rotation plan
- Export CSV ไม่จำกัด range พร้อม custom column
- User ไม่จำกัด
- Dedicated support (response ภายใน 4 ชั่วโมง รวม weekend สำหรับ critical)
- Target uptime 99.9% (SLA อยู่ระหว่างเตรียม — Q3/2026)
- Onboarding session 3 ครั้ง พร้อม custom setup
- Option: on-premise deployment (setup fee แยกต่างหาก)

### ช่วงราคา CC:
| ขนาด | ราคาโดยประมาณ |
|------|-------------|
| 200–350 ห้อง | 15,000 บาท/เดือน |
| 351–500 ห้อง | 17,500 บาท/เดือน |
| 500+ ห้อง | ติดต่อทีมเพื่อ custom quote |

### คำถามที่ CC มักถาม:
- **SLA 99.9% มีจริงไหม?** อยู่ระหว่างเตรียม contract SLA — Q3/2026 — ปัจจุบัน target 99.9% แต่ยังไม่มี penalty clause
- **Audit Log พร้อมเมื่อไหร่?** Q2/2026 — ถ้าเป็น blocker ติดต่อทีมเพื่อ priority access
- **Reference ลูกค้า?** ระบบยังอยู่ระหว่าง early access — ยินดีจัด demo ด้วยข้อมูล anonymized

---

## ทดลองใช้ฟรี

**ทุกแพลน: ทดลองใช้ฟรี 30 วัน ไม่ต้องใส่บัตรเครดิต**

ทีมช่วย setup ให้ฟรีในช่วงทดลองใช้

---

## เปรียบเทียบแพลน

| Feature | CA 390 | CB 1,490 | CC 15,000+ |
|---------|:------:|:--------:|:----------:|
| จำนวนห้อง | ≤ 20 | ≤ 200 | ไม่จำกัด |
| Multi-building Dashboard | - | v | v |
| Report แยกตึก | - | v | v |
| Export CSV multi-month | - | v | v |
| Role Hierarchy 3 ชั้น | - | - | v |
| Audit Log (old→new value) | - | - | v |
| REST API | - | - | v |
| Right to be Forgotten | - | - | v |
| SMS Notification | - | v | v |
| Data Import Wizard | - | v | v |
| Uptime target | 99.5% | 99.5% | 99.9% |
| Support response | 1 วันทำการ | 4 ชม. | 4 ชม. (incl. weekend critical) |
| On-premise option | - | - | v |

---

## ติดต่อ

- LINE OA: @dms-th (placeholder)
- Email: sales@dms.th (placeholder)
- ทีมพร้อมจัด demo call สำหรับ CB และ CC
