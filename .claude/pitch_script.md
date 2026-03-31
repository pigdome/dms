# DMS Pitch Script — Dormitory Management System
## เตรียมโดย: @agent-marketing | อัปเดต: 2026-03-31 (Sprint 1-3 Release)

---

## PART 1: Feature Highlight 5 อันดับแรกของ DMS

### Feature 1 — Smart Billing + PromptPay QR อัตโนมัติ
ระบบออกบิลอัตโนมัติทุกเดือน คำนวณค่าน้ำ/ไฟจากมิเตอร์ที่บันทึกไว้ รองรับ pro-rate กรณีผู้เช่าเข้า/ออกกลางเดือน สร้าง QR PromptPay ผ่าน TMR Gateway ให้ผู้เช่าสแกนจ่ายได้เลย ระบบรับ Webhook ยืนยันการชำระเงินและอัปเดตสถานะบิลอัตโนมัติ ป้องกัน double-charge ด้วย Idempotency Key

### Feature 2 — Dunning อัตโนมัติผ่าน LINE + SMS
ระบบทวงบิลอัตโนมัติ 7 ขั้น (pre_7d / pre_3d / pre_1d / due / post_1d / post_7d / post_15d) ส่งแจ้งเตือนผ่าน LINE หรือ SMS หรือทั้งคู่ โดยไม่ต้องมีคนนั่งทำเอง รองรับ fallback: ถ้า LINE ล้มเหลวระบบส่ง SMS แทนโดยอัตโนมัติ

### Feature 3 — Dashboard ภาพรวมรายได้และห้องพัก
หน้า Dashboard เดียวแสดง: ห้องว่าง/มีคน/ซ่อมบำรุง, รายได้เดือนนี้, บิลค้างชำระ, และ Maintenance Ticket ที่ยังเปิดอยู่ รองรับหลายตึกในหน้าเดียว ไม่ต้องสลับ tab หรือเปิดสมุดบัญชีเอง

### Feature 4 — จัดการซ่อมบำรุงครบวงจร (Maintenance Tracker)
ผู้เช่าแจ้งซ่อมผ่าน Tenant Portal เจ้าของหอเห็น Ticket พร้อมรูปถ่ายก่อน/หลังซ่อม ติดตาม status ตั้งแต่รับเรื่อง จัดช่าง จนปิด Ticket มี Activity Log บันทึกทุก action ว่าใครทำอะไรเมื่อไหร่

### Feature 5 — Digital Vault + Tenant Portal
เก็บเอกสารผู้เช่าออนไลน์ (บัตรประชาชน, สัญญาเช่า, รูปห้อง) เข้ารหัส id_card_no ตาม PDPA ผู้เช่าเข้า Tenant Portal ดูบิล ประวัติการจ่าย แจ้งซ่อม และรับพัสดุผ่าน LINE ได้ทันที

---

## PART 2: Pitch Script แยกตามกลุ่มลูกค้า

---

### CA — หอเล็ก (1 ตึก 5-10 ห้อง)
**Pain Point:** อยากประหยัดเวลา ราคาต้องถูก ไม่มีทีม IT

---

**Opening:**
"คุณจัดการหอคนเดียวอยู่ใช่ไหมครับ? ทุกเดือนต้องนั่งคิดบิลเอง เก็บเงินเอง ส่งข้อความทวงเอง ใช้เวลาไปกี่ชั่วโมงต่อเดือน?"

**Feature Walk-through:**

1. **ออกบิลแบบ 3 คลิก**
   "กด Meter Reading บันทึกเลขมิเตอร์น้ำ/ไฟด้วยมือถือ ถ่ายรูปมิเตอร์แนบไว้เป็นหลักฐาน กด Generate Bill — ระบบคำนวณให้หมด ส่ง QR PromptPay ให้ผู้เช่าผ่าน LINE ทันที"

2. **ทวงบิลอัตโนมัติ LINE + SMS — ไม่ต้องโทรเอง**
   "ตั้ง Dunning ครั้งเดียว ระบบส่ง LINE แจ้งเตือนก่อนครบ 3 วัน วันครบกำหนด และตามทวงหลังค้าง ถ้าผู้เช่าบางคนไม่มี LINE ระบบส่ง SMS แทนได้ทันที ไม่ต้องเขินใจโทรหาผู้เช่าเอง"

3. **Setup Wizard ใช้งานได้ใน 15 นาที**
   "มี Wizard พาทำทีละขั้น ตั้งชื่อหอ เพิ่มห้อง ใส่อัตราค่าน้ำ/ไฟ เสร็จแล้วใช้งานได้เลย ไม่ต้องให้ IT มาช่วย"

4. **ไม่ต้องกังวลเรื่อง Server หรือ Hardware (Sprint 3 — Hosting Info)**
   "ระบบรันบน Web browser ใช้มือถือหรือ laptop ก็ได้ ไม่ต้องซื้อ server ไม่ต้องติดตั้งโปรแกรม ข้อมูลของคุณถูกดูแลอย่างปลอดภัย มีเอกสาร FAQ อธิบายการเก็บข้อมูลแบบเข้าใจง่าย"

5. **Audit Log ใช้งานง่าย — ไม่ต้องกลัวพนักงานแก้ข้อมูล (Sprint 1)**
   "ถึงแม้ CA จะจัดการคนเดียว แต่ถ้าเริ่มมีพนักงานช่วย ระบบบันทึกทุก action ว่าใครเปลี่ยนอะไร ค่าเช่าเดิมเท่าไหร่ แก้เป็นเท่าไหร่ — ป้องกันปัญหาได้ตั้งแต่เนิ่นๆ"

**Closing:**
"10 ห้อง เดือนนึงประหยัดเวลาคำนวณบิล+ทวงเงินได้อย่างน้อย 4-5 ชั่วโมง คุณเอาเวลานั้นไปทำอะไรที่คุ้มค่ากว่าได้เยอะครับ และเมื่อหอโตขึ้น ระบบก็โตตามได้ทันที"

---

**Key Selling Points สำหรับ CA:**
- ใช้งานได้คนเดียว ไม่ต้องมีทีม
- Setup Wizard เริ่มใช้งานได้ภายใน 15 นาที
- ออกบิล + QR PromptPay + ทวงบิล LINE/SMS อัตโนมัติในระบบเดียว
- ไม่ต้องซื้อ hardware เพิ่ม รันบนมือถือหรือ laptop ได้เลย
- มีเอกสาร Hosting Info + PDPA FAQ ให้อ่านก่อนตัดสินใจ
- ราคาเหมาะสมกับขนาดหอ (จ่ายตามห้องที่มี)

**Sprint 1-3 Features ที่เน้นสำหรับ CA:**
- Hosting Info Page + PDPA FAQ — ตอบคำถาม "ข้อมูลอยู่ที่ไหน ปลอดภัยไหม"
- SMS Notification — รองรับผู้เช่าที่ไม่มี LINE
- Audit Log พื้นฐาน — เริ่มใช้ตั้งแต่ก่อนขยายทีม

---

### CB — หอกลาง (3 ตึก 30-50 ห้อง/ตึก)
**Pain Point:** จัดการหลายตึกยุ่งยาก อยากเห็น overview

---

**Opening:**
"ตอนนี้คุณดูแล 3 ตึงพร้อมกัน ทีมพนักงานแต่ละตึกทำงานไม่ sync กัน เวลาอยากรู้ว่าตึงไหนมีห้องว่างหรือบิลค้างเท่าไหร่ ต้องโทรถามหรือไปดูเองทุกครั้ง — ใช่ไหมครับ?"

**Feature Walk-through:**

1. **Dashboard ภาพรวมทุกตึก หน้าเดียว**
   "เห็น occupancy ของทุกตึกในเวลาเดียวกัน ห้องว่าง ห้องค้างชำระ Maintenance Ticket ที่ยังค้างอยู่ในแต่ละตึก ไม่ต้อง login หลายระบบ"

2. **Role Hierarchy: Owner > Building Manager > Staff (Sprint 2)**
   "ใหม่ใน Sprint 2 — ตอนนี้มี role 'Building Manager' ที่เห็นแค่ตึกที่ได้รับมอบหมาย คุณ assign ตึก A ให้ผู้จัดการ A ตึง B ให้ผู้จัดการ B ข้อมูลไม่ปนกัน Owner ยังเห็นทุกอย่างเหมือนเดิม"

3. **Report View รายตึก (Sprint 2)**
   "เปิดหน้า /reports/ เห็นรายได้ อัตราการเข้าพัก และบิลค้างชำระแยกทีละตึง เลือกดูเดือนไหนก็ได้ เปรียบเทียบ performance ระหว่างตึงได้ทันที"

4. **Import Wizard — เพิ่มห้อง/ผู้เช่าด้วย Excel (Sprint 2)**
   "ถ้ามีห้องอยู่แล้ว 50 ห้อง ไม่ต้องกรอกทีละห้อง Download template Excel กรอกข้อมูลห้อง/ผู้เช่า upload เดียว ระบบ validate และ import ให้หมด ถ้า error ระบบ rollback ทั้งหมด ไม่มีข้อมูลค้างครึ่งทาง"

5. **SMS Notification Channel — รองรับผู้เช่าไม่มี LINE (Sprint 2)**
   "หอกลางมีผู้เช่าหลายกลุ่ม บางคนใช้ LINE บางคนไม่ใช้ ตอนนี้ระบบส่งแจ้งเตือนได้ทั้ง LINE และ SMS เลือกตาม preference ของผู้เช่าแต่ละคน หรือตั้ง fallback อัตโนมัติ"

6. **Backend Permission Enforcement + IDOR Protection (Sprint 1)**
   "พนักงานตึก A ไม่สามารถเข้าถึงข้อมูลตึง B ได้แม้จะรู้ URL ระบบ lock ที่ระดับ query ทุกอัน ป้องกัน data leak ระหว่างตึงโดยสมบูรณ์"

**Closing:**
"3 ตึก 150 ห้อง ถ้าเจ้าของหอเห็นทุกอย่างในหน้าจอเดียว มอบหมายงานแต่ละตึกได้ และ import ข้อมูลเดิมด้วย Excel — ไม่ต้องเริ่มต้นใหม่จากศูนย์ นั่นคือ value ที่ DMS ให้คุณได้ครับ"

---

**Key Selling Points สำหรับ CB:**
- Dashboard รวมทุกตึกในหน้าเดียว ไม่ต้องสลับ tab
- Role Hierarchy ใหม่: Owner > Building Manager > Staff — assign ตึกได้
- Report รายตึก: รายได้, occupancy, บิลค้าง — เลือกเดือนได้
- Import Excel: เพิ่มห้อง/ผู้เช่าทีเดียวหลายร้อยรายการ
- SMS + LINE Notification — ไม่มีผู้เช่าคนไหนพลาดการแจ้งเตือน
- IDOR Protection — พนักงานเข้าถึงได้เฉพาะข้อมูลที่ได้รับอนุญาต

**Sprint 1-3 Features ที่เน้นสำหรับ CB:**
- Role Hierarchy (Task 2.1) — deal-maker สำหรับ CB หลายตึก
- Report View per-building (Task 2.2) — overview ที่ CB ต้องการ
- Import Wizard (Task 2.3) — ลด friction ในการ onboard
- SMS Channel (Task 2.4) — ครอบคลุมผู้เช่าทุกกลุ่ม
- Backend Permission (Task 1.3) — ความมั่นใจด้าน security

---

### CC — หอใหญ่ (5-10 ตึก 300+ ห้อง)
**Pain Point:** ต้องการ report ละเอียด scale ได้ ข้อมูลต้องเชื่อถือได้ PDPA compliant

---

**Opening:**
"ระดับ 5-10 ตึง 300+ ห้อง สิ่งที่คุณต้องการไม่ใช่แค่ระบบจัดการหอ — แต่คือ Enterprise Platform ที่มี audit trail ครบ export ข้อมูลได้ทุกเมื่อ compliant กับ PDPA และพร้อม integrate กับ system อื่นๆ ในองค์กร"

**Feature Walk-through:**

1. **Audit Log พร้อม Old/New Value Tracking (Sprint 1 — CC Deal-Breaker)**
   "ทุก action สำคัญในระบบถูกบันทึกแบบ before/after: ใครเปลี่ยนค่าเช่าห้อง 301 จากเท่าไหร่เป็นเท่าไหร่ เมื่อวันไหน เวลาอะไร ดูย้อนหลังได้ที่ /audit-log/ พร้อม filter ตาม model, action, user นี่คือสิ่งที่ระบบ SaaS ทั่วไปไม่มี"

2. **Export CSV Multi-Month Range (Sprint 1 — CC Deal-Breaker)**
   "เลือก start_month และ end_month เดียว ได้ CSV ครบทุกเดือน ทุกตึก รายได้แยกรายห้อง เปิดใน Excel ได้ทันที encode UTF-8 BOM รองรับภาษาไทย ไม่มี N+1 query — export 12 เดือน x 500 ห้องได้ใน seconds"

3. **Role Hierarchy ครบ 4 ชั้น: SuperAdmin > Owner > Building Manager > Staff (Sprint 2)**
   "Assign Building Manager ดูแลเฉพาะตึงที่รับผิดชอบ ไม่ข้ามตึง Owner เห็นทั้งองค์กร Staff ทำงานได้แค่ scope ของตัวเอง ระบบ enforce ที่ระดับ queryset ทุก request ไม่มีทางข้ามได้"

4. **Report View per-Building Breakdown (Sprint 2)**
   "หน้า /reports/ แสดงรายได้ อัตราการเข้าพัก และบิลค้างชำระแยกทีละตึงในหน้าเดียว ใช้ database-level aggregation ด้วย annotate() ไม่มี N+1 ความเร็วคงที่ไม่ว่าจะมีกี่ตึง"

5. **REST API Layer + Swagger Docs (Sprint 3 — CC Enterprise Feature)**
   "DRF API พร้อม Token authentication per-dormitory เชื่อมต่อกับ BI tool, Excel Power Query, หรือ in-house system ขององค์กรได้ทันที Rate limiting ป้องกัน abuse Swagger docs พร้อมให้ developer ทีม IT ใช้งาน Tenant isolation enforce ทุก API call"

6. **PDPA Right to be Forgotten (Sprint 3 — CC Compliance)**
   "Soft delete + Data anonymization ครบตาม PDPA มาตรา 19 (Right to Erasure): ลบ TenantProfile แบบ soft delete เก็บประวัติทางบัญชีไว้ครบ anonymize ข้อมูลส่วนบุคคลออกหลังพ้น retention period AES-256 encryption บน id_card_no ทุก record Purge action บันทึกใน Audit Log เป็น immutable record ลดความเสี่ยงทางกฎหมายได้ทันที"

7. **PDPA Documentation + Hosting Info (Sprint 3)**
   "มีเอกสาร PDPA Compliance ครบสำหรับกระบวนการตัดสินใจของ CC พร้อม FAQ data hosting เพื่อนำเสนอต่อ legal team หรือ board ได้เลย"

**Closing:**
"Audit Log, CSV Export, REST API, PDPA, Role Hierarchy — ทุก deal-breaker ของคุณถูกแก้ครบใน Sprint 1-3 ระบบพร้อม scale จาก 300 ห้องไปถึง 2,000 ห้องโดยไม่ต้องเปลี่ยน architecture นี่คือ Enterprise Dormitory Platform ที่ออกแบบมาสำหรับขนาดของคุณโดยเฉพาะครับ"

---

**Key Selling Points สำหรับ CC:**
- Audit Log with Old/New Values — เห็นทุกการเปลี่ยนแปลงย้อนหลังได้
- Export CSV Multi-Month Range — วิเคราะห์ข้อมูลใน Excel/BI ได้ทุกเมื่อ
- REST API + Token Auth + Swagger — integrate กับ system อื่นๆ ในองค์กร
- PDPA Right to be Forgotten — AES-256, soft delete, anonymization ครบ
- Role Hierarchy 4 ชั้น — จัดการ permission ระดับ Enterprise
- Report per-Building — ตัดสินใจเชิงธุรกิจด้วย data จริง
- Backend IDOR Protection — Security ระดับที่ Enterprise ต้องการ
- 263 tests passing — Quality assurance พร้อม production

**Sprint 1-3 Features ที่เน้นสำหรับ CC (ตาม deal-breaker):**
- Audit Log (Task 1.1) — deal-breaker #1 สำหรับ CC
- Export CSV (Task 1.2) — deal-breaker #2 สำหรับ CC
- Backend Permissions (Task 1.3) — Enterprise security requirement
- Role Hierarchy (Task 2.1) — multi-building management at scale
- Report View (Task 2.2) — business intelligence layer
- REST API (Task 3.1) — integration with enterprise systems
- PDPA (Task 3.2) — legal compliance requirement
- Hosting + PDPA Docs (Task 3.3) — close the deal with legal/board

---

## PART 3: Feature Comparison Matrix

| Feature | CA (หอเล็ก) | CB (หอกลาง) | CC (หอใหญ่) |
|---------|:-----------:|:-----------:|:-----------:|
| Smart Billing + PromptPay QR | หลัก | หลัก | หลัก |
| Dunning อัตโนมัติ LINE | สำคัญมาก | สำคัญมาก | สำคัญมาก |
| SMS Notification Channel | เสริม | สำคัญมาก | สำคัญมาก |
| Dashboard ภาพรวม | พื้นฐาน | หลัก | หลัก |
| Multi-Building Management | ไม่จำเป็น | หลัก | หลัก |
| Role Hierarchy (Building Manager) | ไม่จำเป็น | สำคัญมาก | หลัก |
| Report per-Building | ไม่จำเป็น | สำคัญมาก | หลัก |
| Export CSV Multi-Month | เสริม | เสริม | หลัก (deal-breaker) |
| Audit Log + Old/New Values | เสริม | เสริม | หลัก (deal-breaker) |
| Backend IDOR Protection | เสริม | สำคัญมาก | หลัก |
| Import Wizard (Excel) | เสริม | หลัก | หลัก |
| Maintenance Tracker | เสริม | หลัก | หลัก |
| Broadcast (LINE) | เสริม | หลัก | หลัก |
| Digital Vault + PDPA Encrypt | เสริม | เสริม | หลัก |
| PDPA Right to be Forgotten | ไม่จำเป็น | ไม่จำเป็น | หลัก |
| REST API + Swagger | ไม่จำเป็น | ไม่จำเป็น | หลัก |
| Setup Wizard (Onboarding) | หลัก | เสริม | ไม่จำเป็น |
| Hosting Info + PDPA Docs | สำคัญมาก | เสริม | หลัก |

---

## PART 4: Sprint 1-3 Feature Summary (สำหรับ Pitch Session)

### Sprint 1 — "Security & Foundation" (Delivered 2026-03-30)

| Feature | CA | CB | CC | ใช้ใน Pitch |
|---------|:--:|:--:|:--:|-------------|
| Audit Log + Old/New Values | mention | mention | LEAD | "ดูว่าใครเปลี่ยนอะไร ค่าเดิมเท่าไหร่" |
| Export CSV Multi-Month | skip | mention | LEAD | "download ข้อมูล 12 เดือนด้วยคลิกเดียว" |
| Backend Permission + IDOR | skip | mention | LEAD | "พนักงานข้ามตึกไม่ได้ แม้รู้ URL" |

### Sprint 2 — "Enterprise + Multi-Building" (Delivered 2026-03-31)

| Feature | CA | CB | CC | ใช้ใน Pitch |
|---------|:--:|:--:|:--:|-------------|
| Role Hierarchy (Building Manager) | skip | LEAD | LEAD | "assign ตึกให้ผู้จัดการได้" |
| Report per-Building | skip | LEAD | LEAD | "รายได้ + occupancy รายตึง ในหน้าเดียว" |
| Import Wizard (Excel) | mention | LEAD | LEAD | "import ผู้เช่า 150 คนด้วย Excel ไฟล์เดียว" |
| SMS Notification | mention | LEAD | mention | "ผู้เช่าไม่มี LINE ก็รับแจ้งเตือนได้" |

### Sprint 3 — "Enterprise Extras & PDPA" (Delivered 2026-03-31)

| Feature | CA | CB | CC | ใช้ใน Pitch |
|---------|:--:|:--:|:--:|-------------|
| REST API + Swagger | skip | skip | LEAD | "connect กับ BI tool หรือ in-house system ได้" |
| PDPA Right to be Forgotten | skip | skip | LEAD | "AES-256, soft delete, anonymize ครบ" |
| Hosting Info + PDPA Docs | LEAD | mention | LEAD | "ข้อมูลอยู่ที่ไหน ปลอดภัยอย่างไร" |

---

## PART 5: Objection Handling (Quick Reference — Updated Sprint 1-3)

| Objection | กลุ่ม | คำตอบ |
|-----------|-------|-------|
| "ราคาแพงเกินไป" | CA | "คิดเป็นชั่วโมงที่ประหยัดได้ต่อเดือน คุ้มกว่าแน่นอน" |
| "ต้องมี IT ดูแลไหม?" | CA | "ไม่ต้อง Setup Wizard ทำได้คนเดียวใน 15 นาที ไม่ต้อง install อะไรเพิ่ม" |
| "ข้อมูลเก็บที่ไหน ปลอดภัยไหม?" | CA | "ดูได้เลยที่หน้า Hosting Info — มีคำอธิบายชัดเจน ไม่มีศัพท์เทคนิค" |
| "ระบบซับซ้อนเกินไป" | CB | "แต่ละ role เห็นแค่หน้าที่ตัวเองต้องใช้ ไม่ overwhelming" |
| "Staff ข้ามตึกกันได้ไหม?" | CB | "ไม่ได้ Building Manager เห็นแค่ตึงที่ assign ให้ enforce ที่ระดับ DB" |
| "import ข้อมูลเดิมได้ไหม?" | CB | "ได้เลย มี Excel template ให้ download กรอกแล้ว upload ระบบ validate ให้" |
| "ไม่มี Audit Log" | CC | "มีครับ Sprint 1 — บันทึก old/new value ทุก action ดูที่ /audit-log/" |
| "export CSV ได้ไหม?" | CC | "ได้ เลือก range หลายเดือน แยก building UTF-8 BOM รองรับ Excel ไทย" |
| "มี API ให้ต่อกับ system เราได้ไหม?" | CC | "มี DRF REST API พร้อม Swagger docs Token auth ต่อกับ BI tool ได้เลย" |
| "PDPA ครบไหม?" | CC | "ครบ: AES-256, soft delete, anonymize, purge log ใน audit trail มีเอกสารประกอบ" |
| "ข้อมูลหอเราปลอดภัยไหม?" | CC | "Multi-Tenant isolation ระดับ DB query ทุกอัน lock tenant_id + IDOR protection" |
| "ถ้าระบบล่ม?" | CC | "Docker + PostgreSQL พร้อม backup strategy SLA discussion ขอนัด follow-up" |

---

## PART 6: Conversion Status (จาก Sprint Plan)

| Segment | ก่อน Sprint 1 | หลัง Sprint 1 | หลัง Sprint 3 | สถานะ |
|---------|:------------:|:------------:|:------------:|-------|
| CA | 80% | 85% | 90% | Hosting FAQ + SMS ตอบ concerns ครบ |
| CB | 80% | 88% | 95% | Role Hierarchy + Import + SMS ครบ |
| CC | 60% | 90% | 95%+ | ทุก deal-breaker ถูก remove แล้ว |

**Open Items สำหรับปิด CC:**
- SLA commitment (99.9% uptime) — รอ infra team ยืนยัน
- Demo data (300+ rooms sample) — รอ marketing จัดเตรียม
- Pricing confirmation: CC range 15,000-20,000 THB/mo — รอ MD confirm

---

*เอกสารนี้จัดทำเพื่อใช้ใน Pitch Session Sprint 1-3 Release — อัปเดตจาก feedback ของลูกค้าทั้ง 3 segment*
*Version: Sprint 1-3 | Updated: 2026-03-31 | 263/263 tests passing*
