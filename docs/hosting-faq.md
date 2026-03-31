# Hosting FAQ — DMS Dormitory Management System

Last updated: 2026-03-31

---

## คำถามพื้นฐาน

### ต้องซื้อ hardware เพิ่มไหม?

ไม่ต้องซื้ออะไรเพิ่มเลย

DMS เป็น web-based application ทั้งหมด เจ้าของหอและพนักงานใช้งานผ่าน browser ปกติบนมือถือหรือคอมพิวเตอร์ที่มีอยู่แล้ว ไม่ต้องติดตั้งโปรแกรมพิเศษ ไม่ต้องมีเครื่อง server ในหอพัก

อุปกรณ์ที่ใช้ได้:
- สมาร์ตโฟน Android หรือ iOS
- แท็บเล็ต
- คอมพิวเตอร์ Windows, Mac, Linux
- เปิดด้วย Chrome, Safari, Firefox ได้ทุกตัว

---

## เซิร์ฟเวอร์เก็บข้อมูลที่ไหน?

### ตัวเลือก 1: Cloud (แนะนำสำหรับหอทั่วไป)

ระบบรันบน Docker Container บน cloud provider ในประเทศไทย รองรับ:

- **AWS Bangkok Region (ap-southeast-7)** — data center ตั้งอยู่ในไทย
- **True IDC / NIPA Cloud** — สำหรับลูกค้าที่ต้องการ local cloud ไทย 100%

ข้อมูลทั้งหมดจัดเก็บและประมวลผลในประเทศไทย ไม่ออกนอกประเทศ

### ตัวเลือก 2: On-Premise (สำหรับองค์กรขนาดใหญ่)

สำหรับหอพักระดับ enterprise ที่มี IT team ของตัวเอง รองรับการติดตั้งบน server ของลูกค้าเอง ผ่าน Docker Compose

ข้อกำหนด minimum:
- Server หรือ VM: 2 vCPU, RAM 4 GB, Disk 50 GB
- OS: Ubuntu 22.04+ หรือ Debian 12+
- Docker Engine 24+ และ Docker Compose v2
- Internet connection สำหรับ LINE Messaging API และ TMR Payment

---

## Data Backup

### Cloud Plan

- **Daily backup อัตโนมัติ** — สำรองข้อมูลทุกวันเวลา 02:00 น.
- **Retention 30 วัน** — กู้คืนข้อมูลย้อนหลังได้ 30 วัน
- **Point-in-time recovery** — PostgreSQL WAL archiving รองรับการกู้คืนถึงระดับชั่วโมง
- **File backup** — รูปถ่ายมิเตอร์, เอกสาร lease, รูปพัสดุ — สำรองพร้อมกันกับ database

### On-Premise Plan

ทีม IT ของลูกค้ารับผิดชอบ backup เอง ระบบมี script ช่วย (`manage.py backup`) และ documentation วิธี setup automated backup บน cron

---

## Uptime Commitment

### ความจริงที่ควรรู้

เราเป็นทีมพัฒนาขนาดเล็ก ไม่ได้ให้ SLA 99.99% เหมือน hyperscaler รายใหญ่

**Cloud Standard Plan:** target uptime 99.5% (~44 ชั่วโมง downtime/ปี)
- Maintenance window: อาทิตย์ 01:00–03:00 น.
- ไม่มี dedicated support team ตลอด 24/7

**Cloud Enterprise Plan (CC tier):** target uptime 99.9% (~9 ชั่วโมง downtime/ปี)
- Maintenance window แจ้งล่วงหน้า 48 ชั่วโมงเสมอ
- Support response time: ภายใน 4 ชั่วโมงในวันทำการ
- Incident response: ภายใน 1 ชั่วโมง

หมายเหตุ: SLA แบบ 99.9% พร้อม penalty clause — อยู่ระหว่างพัฒนา กำหนดเปิดให้บริการ Q3/2026

---

## Security ของข้อมูล

- ข้อมูลทั้งหมด encrypt ระหว่างส่ง (HTTPS/TLS 1.3)
- Database encrypt at rest
- ข้อมูลสำคัญ เช่น เลขบัตรประชาชน — encrypt ด้วย AES-256 ดู [pdpa-compliance.md](pdpa-compliance.md)
- แต่ละหอพักข้อมูลแยกกันสมบูรณ์ (Multi-tenant isolation) ไม่สามารถเห็นข้อมูลหอพักอื่นได้เด็ดขาด

---

## คำถามที่ CA มักถาม

**Q: ถ้า internet ดับ ใช้งานได้ไหม?**
A: ไม่ได้ เพราะเป็น web app ต้องการ internet ตลอด — แต่ใช้งานหลัก (จ่ายบิล, ดูข้อมูลห้อง) สามารถ cache บางส่วนบนมือถือได้ในอนาคต (roadmap)

**Q: ถ้าเปลี่ยนใจไม่ใช้แล้ว ข้อมูลได้คืนไหม?**
A: ได้ export ข้อมูลทั้งหมดเป็น CSV ได้ตลอดเวลา ไม่มี lock-in

**Q: ราคา cloud กับ on-premise ต่างกันไหม?**
A: Cloud plan ราคาตาม [pricing-guide.md](pricing-guide.md) — On-premise มี setup fee เพิ่ม ติดต่อทีมโดยตรง
