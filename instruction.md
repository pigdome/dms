# 🚀 Project Brief: Dormitory Management System (DMS)

**Version:** 1.0 (2026 Edition)
**Platform:** LINE Mini App (LIFF)
**Architecture:** Multi-Tenant SaaS (รองรับหลายเจ้าของ/หลายหอพักในระบบเดียว)

---

## 📌 1. Project Overview

ระบบบริหารจัดการหอพักแบบครบวงจรที่เน้นการใช้งานผ่าน LINE เพื่อลดภาระเจ้าของหอพักในด้านการเก็บเงิน การตามหนี้ และการสื่อสาร โดยตัดความซับซ้อนด้านระบบบัญชีออก แต่เน้นความแม่นยำของการรับเงินและการจัดการรายวัน

---

## 👤 2. User Roles & Permissions

ระบบต้องรองรับการแยกสิทธิ์การใช้งาน (RBAC) ดังนี้:

* **Superadmin (System Owner):**
* จัดการบัญชีเจ้าของหอพัก (Create/Suspend Client Accounts)
* ดูสถิติภาพรวมและการใช้งานของทั้งระบบ
* ตั้งค่า Global Config และระบบชำระเงินส่วนกลาง

* **Owner (Client Admin):**
* จัดการได้เฉพาะหอพัก/ตึกของตัวเองเท่านั้น (**Data Isolation**)
* จัดการห้องพัก (Add/Edit Rooms) และผู้เช่า (Tenant Mapping)
* ตั้งค่าราคาค่าเช่า ค่าน้ำ/ไฟ และเชื่อมต่อ Payment Gateway ของตัวเอง
* สร้างบัญชีพนักงาน (Staff) และกำหนดสิทธิ์แต่ละคน
* ดู Audit Log ของกิจกรรมทั้งหมดในหอพักตัวเอง

* **Staff (Limited):**
* สิทธิ์จำกัดตามที่ Owner กำหนด เช่น จดมิเตอร์, แจ้งพัสดุ, อัปเดตสถานะซ่อม
* ไม่สามารถเข้าถึงข้อมูลการเงินหรือสัญญาเช่าได้ (ถ้า Owner ไม่อนุญาต)

* **User (Tenant):**
* ใช้งานผ่าน LINE Mini App เห็นเฉพาะข้อมูลห้องที่ตัวเองเช่า
* ดูยอดค้างชำระ ชำระเงิน แจ้งซ่อม และรับการแจ้งเตือนพัสดุ

### Permission Matrix (สรุปสิทธิ์)

| Action | Superadmin | Owner | Staff | Tenant |
|---|---|---|---|---|
| จัดการบัญชี Owner | ✅ | ❌ | ❌ | ❌ |
| จัดการตึก/ห้อง | ❌ | ✅ | ❌ | ❌ |
| จัดการผู้เช่า | ❌ | ✅ | ❌ | ❌ |
| จดมิเตอร์ | ❌ | ✅ | ✅ | ❌ |
| แจ้งพัสดุ | ❌ | ✅ | ✅ | ❌ |
| ดูข้อมูลการเงิน | ❌ | ✅ | ❌ | ตัวเอง |
| ชำระเงิน | ❌ | ❌ | ❌ | ✅ |
| แจ้งซ่อม | ❌ | ✅ | ✅ | ✅ |
| ดู Audit Log | ❌ | ✅ | ❌ | ❌ |

---

## 🛠️ 3. Core Features Requirements

### 3.1 ระบบการเงินและชำระเงิน (Payment & Billing)

* **Billing Engine:** คำนวณค่าเช่าอัตโนมัติ (Base Price + Meter Units)
  * รอบบิลกำหนดได้ต่อหอพัก (เช่น ตัดทุกวันที่ 1 หรือวันที่กำหนดเอง)
  * รองรับ Pro-rate สำหรับผู้เช่าที่เข้า/ออกกลางเดือน
* **Payment Gateway (Integration):** สร้าง Dynamic QR Code (PromptPay) ตามยอดจริง
  * ใช้ TMR Payment Gateway — Owner กรอก TMR API Key + API Secret ในหน้า Settings
  * ตั้งค่าวันออกบิล (เลือกได้: วันที่ 1, 5, 10, 25 ของเดือน) และ grace period (จำนวนวัน)
  * ตั้งค่าอัตราค่าไฟ (บาท/หน่วย) และค่าน้ำ (บาท/หน่วย) ต่อหอพัก
* **Auto-Verification:** ตรวจสอบยอดเงินเข้าผ่าน Webhook TMR และปรับสถานะบิลเป็น "ชำระแล้ว" ทันที (No Slip Manual Check)
  * รองรับ Idempotency — ป้องกัน Webhook ซ้ำกรณี Gateway ส่งซ้ำ
* **Digital Receipt:** ออกใบเสร็จรับเงินอัตโนมัติเข้า LINE ผู้เช่า
* **Export Report:** Owner สามารถ export ข้อมูลบิล/การชำระเงินรายเดือนเป็น CSV

### 3.2 ระบบลดภาระการดำเนินงาน (Operation Efficiency)

* **Meter Reading Helper (3-step wizard):**
  * เลือกตึก/ห้อง → ระบบดึงเลขมิเตอร์เก่ามาแสดงอัตโนมัติ
  * กรอกเลขมิเตอร์น้ำ + ถ่ายรูปเป็นหลักฐาน
  * กรอกเลขมิเตอร์ไฟ + ถ่ายรูปเป็นหลักฐาน
* **Maintenance Ticket:**
  * สถานะ: มาใหม่ → กำลังซ่อม → รออะไหล่ → เสร็จสิ้น
  * มี timeline แสดงประวัติสถานะทั้งหมด
  * บันทึกช่างผู้รับผิดชอบ
  * แนบรูปภาพปัญหาและรูปภาพหลังซ่อมเสร็จ
  * Owner/Staff โทรหาผู้เช่าได้จากหน้า ticket detail
* **Parcel Notification (Snap & Notify):**
  * ถ่ายรูปพัสดุ → เลือกห้อง → ระบุผู้ขนส่ง → ระบบส่ง LINE ทันที
  * บันทึก log พัสดุทั้งหมด (history)
* **Dunning System:** ระบบทวงเงินอัตโนมัติ ตามลำดับดังนี้:
  * แจ้งเตือนล่วงหน้า 7 วัน, 3 วัน, และ 1 วันก่อนครบกำหนด
  * แจ้งเตือนวันครบกำหนด (Due Date)
  * แจ้งเตือนเมื่อค้างชำระ: +1 วัน, +7 วัน, +15 วัน (Owner กำหนด Schedule ได้)
* **Broadcast Creator:**
  * เลือก audience: ทั้งหมด / ตึก A / ตึก B / รายชั้น
  * เขียน message พร้อมแนบรูปภาพ
  * Preview รูปแบบ LINE OA message ก่อนส่ง
  * ส่งผ่าน LINE OA

### 3.3 ระบบ Dashboard & แจ้งเตือน Owner (Retention Driver)

* **Owner Dashboard:** หน้าแรกที่ Owner เห็นเมื่อเปิดระบบ แสดงภาพรวมทันที:
  * รายได้รวมเดือนนี้ vs เดือนก่อน
  * จำนวนห้องที่ค้างชำระ (พร้อมยอดรวม)
  * จำนวนห้องว่าง
  * งานซ่อมที่ยังค้างอยู่
* **Real-time Payment Notification:** แจ้งเตือน Owner ผ่าน LINE ทันทีเมื่อผู้เช่าชำระเงิน (ระบุห้อง + จำนวนเงิน)
* **Vacancy Tracking:** ติดตามสถานะห้องแต่ละห้อง (ว่าง / มีผู้เช่า / สัญญาใกล้หมด) พร้อมแจ้งเตือนล่วงหน้าเมื่อสัญญาใกล้สิ้นสุด

### 3.4 ระบบ Onboarding & Migration

* **Quick Setup Wizard (3 Steps):** สำหรับ Owner ใหม่:
  1. ข้อมูลอาคาร (ชื่อ, ที่อยู่, รูปภาพ, pin ที่ตั้งบนแผนที่)
  2. ตั้งค่าชั้น/ห้อง
  3. ตั้งค่าอื่นๆ (ราคา, payment gateway)
* **Tenant Onboarding:**
  * รองรับ OCR สแกนบัตรประชาชน เพื่อ auto-fill ข้อมูล
  * กรอกข้อมูลด้วยตนเอง (ชื่อ, เบอร์โทร/LINE ID, ห้อง, วันเข้าพัก)
  * Bulk Import จาก Excel/CSV สำหรับผู้เช่าหลายห้องพร้อมกัน

### 3.5 ระบบจัดการข้อมูลและเอกสาร (Data & Contract)

* **Multi-Building Support:** เจ้าของ 1 ราย สามารถจัดการได้หลายตึกภายใต้บัญชีเดียว
* **Digital Vault:** จัดเก็บสำเนาบัตรประชาชน รูปถ่ายสภาพห้อง และสัญญาเช่าดิจิทัล
  * รองรับไฟล์: JPG, PNG, PDF — ขนาดไม่เกิน 10 MB ต่อไฟล์
  * Storage: Local (ขยายเป็น Cloud ในอนาคต)

---

## 🏗️ 4. Technical Requirements (For Dev)

### 4.1 Tech Stack

* **Backend:** Django admin with theme unfold
* **Frontend:** Django template สำหรับเจ้าของหอ และ ผู้ใช้ (Web or Line Liff)
* **Database:** PostgreSQL (Primary) + Redis (Cache/Queue)
* **File Storage:** Local
* **Hosting:** Docker + Docker compose
* **Queue/Worker:** Redis

### 4.2 Multi-Tenancy & Security

* **Multi-Tenancy:** ออกแบบ Database ให้รองรับ `tenant_id` ในทุก Table เพื่อแยกข้อมูลลูกค้าแต่ละรายอย่างเด็ดขาด
* **LINE Integration:** ใช้ LINE Messaging API สำหรับการแจ้งเตือน และ LIFF SDK สำหรับหน้าจอแอป
* **Security:**
  * รองรับ PDPA — ข้อมูลส่วนบุคคล (ชื่อ, เลขบัตร ฯลฯ) ต้อง encrypt at rest
  * Data Retention: ลบข้อมูลผู้เช่าภายใน 90 วันหลังสิ้นสุดสัญญา (หรือตามที่ Owner กำหนด)
  * Right to Erasure: Owner หรือ Tenant สามารถขอลบข้อมูลส่วนบุคคลได้
* **Scalability:** ออกแบบโครงสร้างให้รองรับการขยายตัวเมื่อมีจำนวนหอพักและผู้เช่าเพิ่มขึ้นในอนาคต

### 4.3 Non-Functional Requirements

* **Uptime:** 99.5% (ยกเว้น Scheduled Maintenance)
* **API Response Time:** P95 < 500ms สำหรับ endpoints หลัก
* **Webhook Processing:** ต้องประมวลผล Payment Webhook ภายใน 5 วินาที
* **Language:** eng แต่ใน template ให้ทำรองรับภาษาไทยและอื่นๆ ในอนาคต

### 4.4 Activity Log:
* บันทึกทุก action สำคัญ (ใคร ทำอะไร เมื่อไหร่)

---

## 🚫 5. Out of Scope (ไม่รวมในขอบเขตงาน)

* **Full Accounting:** ไม่รวมระบบทำงบกำไรขาดทุน หรือระบบภาษีเต็มรูปแบบ
* **Hardware Integration:** ไม่รวมการติดตั้งอุปกรณ์ IoT (เน้นการรับข้อมูลผ่านแอป)

---
