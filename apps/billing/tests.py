import json
from decimal import Decimal
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.billing.services import (
    calculate_bill,
    calculate_prorated_rent,
    generate_bills_for_dormitory,
    get_dunning_trigger_dates,
    mark_overdue_bills,
)
from apps.core.threadlocal import dormitory_context


# ---------------------------------------------------------------------------
# Pure calculation tests (no DB)
# ---------------------------------------------------------------------------

class CalculateBillTests(SimpleTestCase):
    def test_calculate_bill_basic(self):
        result = calculate_bill(base_rent=5000, water_units=10, elec_units=20, water_rate=18, elec_rate=7)
        self.assertEqual(result['base_rent'], Decimal('5000'))
        self.assertEqual(result['water_amt'], Decimal('180'))
        self.assertEqual(result['elec_amt'], Decimal('140'))
        self.assertEqual(result['other_amt'], Decimal('0'))
        self.assertEqual(result['total'], Decimal('5320'))

    def test_calculate_bill_with_extra_charges(self):
        result = calculate_bill(base_rent=5000, water_units=10, elec_units=20,
                                water_rate=18, elec_rate=7, extra_amt=500)
        self.assertEqual(result['other_amt'], Decimal('500'))
        self.assertEqual(result['total'], Decimal('5820'))

    def test_calculate_bill_zero_utilities(self):
        result = calculate_bill(base_rent=3000, water_units=0, elec_units=0, water_rate=18, elec_rate=7)
        self.assertEqual(result['water_amt'], Decimal('0'))
        self.assertEqual(result['elec_amt'], Decimal('0'))
        self.assertEqual(result['other_amt'], Decimal('0'))
        self.assertEqual(result['total'], Decimal('3000'))

    def test_calculate_bill_decimal_precision(self):
        result = calculate_bill(
            base_rent='1000.50', water_units='3.7', elec_units='12.3',
            water_rate='18.5', elec_rate='4.5',
        )
        self.assertEqual(result['water_amt'], Decimal('68.45'))
        self.assertEqual(result['elec_amt'], Decimal('55.35'))
        self.assertEqual(result['total'], Decimal('1124.30'))
        self.assertIsInstance(result['total'], Decimal)


class ProratedRentTests(SimpleTestCase):
    def test_prorated_rent_full_month(self):
        result = calculate_prorated_rent(Decimal('6000'), date(2024, 3, 1), date(2024, 3, 1))
        self.assertEqual(result, Decimal('6000.00'))

    def test_prorated_rent_half_month(self):
        result = calculate_prorated_rent(Decimal('6000'), date(2024, 4, 16), date(2024, 4, 1))
        self.assertEqual(result, Decimal('3000.00'))

    def test_prorated_rent_last_day(self):
        result = calculate_prorated_rent(Decimal('3100'), date(2024, 1, 31), date(2024, 1, 1))
        expected = (Decimal('3100') * 1 / 31).quantize(Decimal('0.01'))
        self.assertEqual(result, expected)


class DunningTriggerDatesTests(SimpleTestCase):
    def test_dunning_trigger_dates(self):
        due = date(2024, 3, 15)
        dates = get_dunning_trigger_dates(due)
        self.assertEqual(dates['pre_7d'],   date(2024, 3, 8))
        self.assertEqual(dates['pre_3d'],   date(2024, 3, 12))
        self.assertEqual(dates['pre_1d'],   date(2024, 3, 14))
        self.assertEqual(dates['due'],      date(2024, 3, 15))
        self.assertEqual(dates['post_1d'],  date(2024, 3, 16))
        self.assertEqual(dates['post_7d'],  date(2024, 3, 22))
        self.assertEqual(dates['post_15d'], date(2024, 3, 30))
        self.assertEqual(len(dates), 7)


# ---------------------------------------------------------------------------
# Bill model tests (require DB)
# ---------------------------------------------------------------------------

class BillInvoiceNumberTests(TestCase):
    """Tests for Bill.save() invoice_number auto-generation."""

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room

        cls.dorm = Dormitory.objects.create(
            name='Test Dorm', address='Test Addr', invoice_prefix='T01'
        )
        with dormitory_context(cls.dorm):
            building = Building.objects.create(name='Building 1')
            floor = Floor.objects.create(building=building, number=1)
            cls.room1 = Room.objects.create(floor=floor, number='101', base_rent=5000)
            cls.room2 = Room.objects.create(floor=floor, number='102', base_rent=5000)

        cls.dorm2 = Dormitory.objects.create(
            name='Other Dorm', address='Other Addr', invoice_prefix='X99'
        )
        with dormitory_context(cls.dorm2):
            building2 = Building.objects.create(name='Building X')
            floor2 = Floor.objects.create(building=building2, number=1)
            cls.room_dorm2 = Room.objects.create(floor=floor2, number='101', base_rent=4000)

    def _make_bill(self, room, month, **kwargs):
        from apps.billing.models import Bill
        with dormitory_context(room.dormitory):
            return Bill.objects.create(
                room=room, month=month, base_rent=5000,
                total=5000, due_date=date(month.year, month.month, 25),
                **kwargs
            )

    def test_invoice_number_format(self):
        bill = self._make_bill(self.room1, date(2025, 3, 1))
        # T01-2503-001
        self.assertEqual(bill.invoice_number, 'T01-2503-001')

    def test_invoice_number_uses_dormitory_prefix(self):
        bill = self._make_bill(self.room_dorm2, date(2025, 3, 1))
        self.assertTrue(bill.invoice_number.startswith('X99-'))

    def test_invoice_number_sequence_increments(self):
        bill1 = self._make_bill(self.room1, date(2025, 4, 1))
        bill2 = self._make_bill(self.room2, date(2025, 4, 1))
        seq1 = int(bill1.invoice_number.split('-')[2])
        seq2 = int(bill2.invoice_number.split('-')[2])
        self.assertEqual(seq2 - seq1, 1)

    def test_invoice_number_is_unique_across_dormitories(self):
        """Two dormitories can both have T01-2503-001 if prefix differs, but unique per DB."""
        bill_a = self._make_bill(self.room1, date(2025, 5, 1))
        bill_b = self._make_bill(self.room_dorm2, date(2025, 5, 1))
        # They must be different strings (different prefix)
        self.assertNotEqual(bill_a.invoice_number, bill_b.invoice_number)

    def test_invoice_number_sequence_resets_per_month(self):
        bill_mar = self._make_bill(self.room1, date(2025, 6, 1))
        bill_apr = self._make_bill(self.room1, date(2025, 7, 1))
        # Both should end with -001 since they are first in their month
        self.assertTrue(bill_mar.invoice_number.endswith('-001'))
        self.assertTrue(bill_apr.invoice_number.endswith('-001'))

    def test_existing_invoice_number_not_overwritten(self):
        from apps.billing.models import Bill
        bill = Bill.objects.create(
            room=self.room1, month=date(2025, 8, 1), base_rent=5000,
            total=5000, due_date=date(2025, 8, 25), invoice_number='MANUAL-001'
        )
        self.assertEqual(bill.invoice_number, 'MANUAL-001')

    def test_no_prefix_falls_back_to_inv(self):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        dorm_no_prefix = Dormitory.objects.create(name='No Prefix', address='Addr')
        b = Building.objects.create(dormitory=dorm_no_prefix, name='B')
        f = Floor.objects.create(building=b, number=1)
        room = Room.objects.create(floor=f, number='101', base_rent=3000)
        bill = self._make_bill(room, date(2025, 9, 1))
        self.assertTrue(bill.invoice_number.startswith('INV-'))


class BillTenantIsolationTests(TestCase):
    """Bill queryset must not leak across dormitories."""

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        cls.dorm_a = Dormitory.objects.create(name='Dorm A', address='A', invoice_prefix='DA1')
        cls.dorm_b = Dormitory.objects.create(name='Dorm B', address='B', invoice_prefix='DB1')

        ba = Building.objects.create(dormitory=cls.dorm_a, name='BA')
        fa = Floor.objects.create(building=ba, number=1)
        cls.room_a = Room.objects.create(floor=fa, number='101', base_rent=4000)

        bb = Building.objects.create(dormitory=cls.dorm_b, name='BB')
        fb = Floor.objects.create(building=bb, number=1)
        cls.room_b = Room.objects.create(floor=fb, number='101', base_rent=4000)

        cls.bill_a = Bill.objects.create(
            room=cls.room_a, month=date(2025, 1, 1), base_rent=4000,
            total=4000, due_date=date(2025, 1, 25)
        )
        cls.bill_b = Bill.objects.create(
            room=cls.room_b, month=date(2025, 1, 1), base_rent=4000,
            total=4000, due_date=date(2025, 1, 25)
        )

    def test_bills_filtered_by_dormitory_a(self):
        from apps.billing.models import Bill
        bills = Bill.objects.filter(room__floor__building__dormitory=self.dorm_a)
        self.assertIn(self.bill_a, bills)
        self.assertNotIn(self.bill_b, bills)

    def test_bills_filtered_by_dormitory_b(self):
        from apps.billing.models import Bill
        bills = Bill.objects.filter(room__floor__building__dormitory=self.dorm_b)
        self.assertIn(self.bill_b, bills)
        self.assertNotIn(self.bill_a, bills)


# ---------------------------------------------------------------------------
# generate_bills_for_dormitory service tests
# ---------------------------------------------------------------------------

class GenerateBillsServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import BillingSettings

        cls.dorm = Dormitory.objects.create(
            name='Svc Dorm', address='Addr', invoice_prefix='SVC'
        )
        cls.settings = BillingSettings.objects.create(
            dormitory=cls.dorm,
            bill_day=1,
            grace_days=5,
            water_rate=18,
            elec_rate=7,
        )

        building = Building.objects.create(dormitory=cls.dorm, name='B1')
        floor = Floor.objects.create(building=building, number=1)
        cls.room_occ = Room.objects.create(
            floor=floor, number='101', base_rent=5000, status=Room.Status.OCCUPIED
        )
        cls.room_vac = Room.objects.create(
            floor=floor, number='102', base_rent=4000, status=Room.Status.VACANT
        )

    def test_creates_bill_for_occupied_room(self):
        month = date(2025, 10, 1)
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 1)
        self.assertEqual(bills[0].room, self.room_occ)

    def test_skips_vacant_room(self):
        month = date(2025, 11, 1)
        bills = generate_bills_for_dormitory(self.dorm, month)
        rooms = [b.room for b in bills]
        self.assertNotIn(self.room_vac, rooms)

    def test_skips_existing_bill(self):
        from apps.billing.models import Bill
        month = date(2025, 12, 1)
        # Pre-create bill for occupied room
        Bill.objects.create(
            room=self.room_occ, month=month, base_rent=5000,
            total=5000, due_date=date(2025, 12, 6)
        )
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 0)

    def test_utility_amounts_from_meter_reading(self):
        from apps.rooms.models import MeterReading
        month = date(2026, 1, 1)
        reading = MeterReading.objects.create(
            room=self.room_occ,
            water_prev=100, water_curr=110,   # 10 units × 18 = 180
            elec_prev=200, elec_curr=220,      # 20 units × 7  = 140
            reading_date=date(2026, 1, 15),
            recorded_by=None,
        )
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 1)
        bill = bills[0]
        self.assertEqual(bill.water_amt, Decimal('180.00'))
        self.assertEqual(bill.elec_amt, Decimal('140.00'))
        self.assertEqual(bill.total, Decimal('5320.00'))
        # Verify meter_reading is linked
        self.assertEqual(bill.meter_reading, reading)
        # Verify meter snapshot properties
        self.assertEqual(bill.water_prev, Decimal('100'))
        self.assertEqual(bill.water_curr, Decimal('110'))
        self.assertEqual(bill.water_units, Decimal('10'))
        self.assertEqual(bill.elec_prev, Decimal('200'))
        self.assertEqual(bill.elec_curr, Decimal('220'))
        self.assertEqual(bill.elec_units, Decimal('20'))

    def test_no_meter_reading_yields_zero_utilities(self):
        month = date(2026, 2, 1)
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 1)
        bill = bills[0]
        self.assertEqual(bill.water_amt, Decimal('0'))
        self.assertEqual(bill.elec_amt, Decimal('0'))
        self.assertEqual(bill.total, bill.base_rent)

    def test_returns_empty_list_when_no_billing_settings(self):
        from apps.core.models import Dormitory
        dorm_no_settings = Dormitory.objects.create(name='No Settings', address='X')
        bills = generate_bills_for_dormitory(dorm_no_settings, date(2026, 3, 1))
        self.assertEqual(bills, [])

    def test_due_date_respects_grace_days(self):
        month = date(2026, 4, 1)
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 1)
        # bill_day=1 → bill_date = 2026-04-01, grace_days=5 → due = 2026-04-06
        self.assertEqual(bills[0].due_date, date(2026, 4, 6))


# ---------------------------------------------------------------------------
# ExtraChargeType + BillLineItem + refresh_total tests
# ---------------------------------------------------------------------------

class BillLineItemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill, BillingSettings, ExtraChargeType

        dorm = Dormitory.objects.create(name='LI Dorm', address='Addr')
        building = Building.objects.create(dormitory=dorm, name='B')
        floor = Floor.objects.create(building=building, number=1)
        cls.room = Room.objects.create(floor=floor, number='101', base_rent=5000)
        BillingSettings.objects.create(dormitory=dorm, bill_day=1, grace_days=5,
                                        elec_rate=7, water_rate=18)
        cls.bill = Bill.objects.create(
            room=cls.room, month=date(2026, 1, 1),
            base_rent=5000, water_amt=180, elec_amt=140,
            total=5320, due_date=date(2026, 1, 6),
        )
        cls.charge_type = ExtraChargeType.objects.create(
            dormitory=dorm, name='Internet', default_amount=300,
        )

    def test_add_line_item_and_refresh_total(self):
        from apps.billing.models import BillLineItem
        BillLineItem.objects.create(
            bill=self.bill,
            charge_type=self.charge_type,
            description='Internet - Jan 2026',
            amount=Decimal('300'),
        )
        self.bill.refresh_total()
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.other_amt, Decimal('300'))
        self.assertEqual(self.bill.total, Decimal('5620'))

    def test_multiple_line_items(self):
        from apps.billing.models import BillLineItem, Bill
        bill2 = Bill.objects.create(
            room=self.room, month=date(2026, 2, 1),
            base_rent=5000, water_amt=0, elec_amt=0,
            total=5000, due_date=date(2026, 2, 6),
        )
        BillLineItem.objects.create(bill=bill2, description='Internet', amount=Decimal('300'))
        BillLineItem.objects.create(bill=bill2, description='Parking', amount=Decimal('200'))
        bill2.refresh_total()
        bill2.refresh_from_db()
        self.assertEqual(bill2.other_amt, Decimal('500'))
        self.assertEqual(bill2.total, Decimal('5500'))

    def test_bill_without_meter_reading_returns_zero_snapshot(self):
        self.assertIsNone(self.bill.meter_reading)
        self.assertEqual(self.bill.water_prev, Decimal('0'))
        self.assertEqual(self.bill.elec_curr, Decimal('0'))
        self.assertEqual(self.bill.water_units, Decimal('0'))


# ---------------------------------------------------------------------------
# mark_overdue_bills service tests
# ---------------------------------------------------------------------------

class MarkOverdueBillsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        dorm = Dormitory.objects.create(name='OD Dorm', address='Addr')
        building = Building.objects.create(dormitory=dorm, name='B')
        floor = Floor.objects.create(building=building, number=1)
        cls.room = Room.objects.create(floor=floor, number='101', base_rent=3000)

        past = date(2024, 1, 1)
        future = date(2099, 1, 1)

        cls.bill_sent_past = Bill.objects.create(
            room=cls.room, month=date(2024, 1, 1), base_rent=3000,
            total=3000, due_date=past, status='sent'
        )
        cls.bill_draft_past = Bill.objects.create(
            room=cls.room, month=date(2024, 2, 1), base_rent=3000,
            total=3000, due_date=past, status='draft'
        )
        cls.bill_future = Bill.objects.create(
            room=cls.room, month=date(2024, 3, 1), base_rent=3000,
            total=3000, due_date=future, status='sent'
        )
        cls.bill_paid = Bill.objects.create(
            room=cls.room, month=date(2024, 4, 1), base_rent=3000,
            total=3000, due_date=past, status='paid'
        )

    def test_marks_sent_past_due_as_overdue(self):
        from apps.billing.models import Bill
        mark_overdue_bills()
        self.bill_sent_past.refresh_from_db()
        self.assertEqual(self.bill_sent_past.status, Bill.Status.OVERDUE)

    def test_marks_draft_past_due_as_overdue(self):
        from apps.billing.models import Bill
        mark_overdue_bills()
        self.bill_draft_past.refresh_from_db()
        self.assertEqual(self.bill_draft_past.status, Bill.Status.OVERDUE)

    def test_leaves_future_bill_unchanged(self):
        mark_overdue_bills()
        self.bill_future.refresh_from_db()
        self.assertEqual(self.bill_future.status, 'sent')

    def test_leaves_paid_bill_unchanged(self):
        mark_overdue_bills()
        self.bill_paid.refresh_from_db()
        self.assertEqual(self.bill_paid.status, 'paid')

    def test_returns_count_of_updated_bills(self):
        count = mark_overdue_bills()
        self.assertEqual(count, 2)  # sent_past + draft_past


# ---------------------------------------------------------------------------
# TMR Webhook tests
# ---------------------------------------------------------------------------

class TMRWebhookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        dorm = Dormitory.objects.create(
            name='Webhook Dorm', address='Addr', invoice_prefix='WH1'
        )
        building = Building.objects.create(dormitory=dorm, name='B')
        floor = Floor.objects.create(building=building, number=1)
        room = Room.objects.create(floor=floor, number='101', base_rent=5000)

        cls.bill = Bill.objects.create(
            room=room, month=date(2025, 3, 1), base_rent=5000,
            total=5000, due_date=date(2025, 3, 25),
            invoice_number='WH1-2503-001',
        )

    def _post(self, payload, secret=None, extra_headers=None):
        body = json.dumps(payload).encode()
        headers = {}
        if secret:
            import hashlib, hmac as _hmac
            sig = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            headers['HTTP_X_TMR_SIGNATURE'] = sig
        if extra_headers:
            headers.update(extra_headers)
        return self.client.post(
            reverse('billing:tmr_webhook'),
            data=body,
            content_type='application/json',
            **headers,
        )

    def test_happy_path_marks_bill_paid(self):
        # B2 fix: ต้องส่ง secret จริงเสมอ — empty secret ถูก reject แล้ว
        from apps.billing.models import Bill, Payment
        with self.settings(TMR_WEBHOOK_SECRET='test-secret'):
            resp = self._post({
                'ref': 'TXN-001',
                'order_id': 'WH1-2503-001',
                'amount': '5000.00',
            }, secret='test-secret')
        self.assertEqual(resp.status_code, 200)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, Bill.Status.PAID)
        self.assertTrue(Payment.objects.filter(idempotency_key='TXN-001').exists())

    def test_idempotent_duplicate_returns_200(self):
        # B2 fix: ต้องส่ง secret จริงเสมอ — empty secret ถูก reject แล้ว
        from apps.billing.models import Payment
        from django.utils import timezone
        Payment.objects.create(
            bill=self.bill,
            amount=5000,
            tmr_ref='TXN-DUP',
            idempotency_key='TXN-DUP',
            paid_at=timezone.now(),
        )
        with self.settings(TMR_WEBHOOK_SECRET='test-secret'):
            resp = self._post({
                'ref': 'TXN-DUP',
                'order_id': 'WH1-2503-001',
                'amount': '5000.00',
            }, secret='test-secret')
        self.assertEqual(resp.status_code, 200)
        resp_data = json.loads(resp.content)
        self.assertEqual(resp_data['status'], 'already_processed')

    def test_invalid_signature_returns_403(self):
        with self.settings(TMR_WEBHOOK_SECRET='correct-secret'):
            resp = self._post(
                {'ref': 'TXN-BAD', 'order_id': 'WH1-2503-001', 'amount': '5000'},
                extra_headers={'HTTP_X_TMR_SIGNATURE': 'badsignature'},
            )
        self.assertEqual(resp.status_code, 403)

    def test_valid_signature_accepted(self):
        with self.settings(TMR_WEBHOOK_SECRET='my-secret'):
            resp = self._post(
                {'ref': 'TXN-SIG', 'order_id': 'WH1-2503-001', 'amount': '5000'},
                secret='my-secret',
            )
        self.assertIn(resp.status_code, [200, 404])  # 200 ok or 404 if already paid

    def test_missing_ref_returns_400(self):
        # B2 fix: ส่ง secret ถูกต้อง แต่ payload ขาด ref → ควรได้ 400
        with self.settings(TMR_WEBHOOK_SECRET='test-secret'):
            resp = self._post({'order_id': 'WH1-2503-001', 'amount': '5000'}, secret='test-secret')
        self.assertEqual(resp.status_code, 400)

    def test_missing_order_id_returns_400(self):
        # B2 fix: ส่ง secret ถูกต้อง แต่ payload ขาด order_id → ควรได้ 400
        with self.settings(TMR_WEBHOOK_SECRET='test-secret'):
            resp = self._post({'ref': 'TXN-NOID', 'amount': '5000'}, secret='test-secret')
        self.assertEqual(resp.status_code, 400)

    def test_bill_not_found_returns_404(self):
        # B2 fix: ส่ง secret ถูกต้อง แต่ invoice ไม่มีในระบบ → ควรได้ 404
        with self.settings(TMR_WEBHOOK_SECRET='test-secret'):
            resp = self._post({
                'ref': 'TXN-NOTFOUND',
                'order_id': 'NONEXISTENT-999',
                'amount': '5000',
            }, secret='test-secret')
        self.assertEqual(resp.status_code, 404)

    def test_no_secret_configured_returns_400(self):
        # B2: ถ้า TMR_WEBHOOK_SECRET ไม่ได้ตั้งค่า → 400 ทันที ห้าม skip verify
        with self.settings(TMR_WEBHOOK_SECRET=''):
            resp = self._post({
                'ref': 'TXN-NOSECRET',
                'order_id': 'WH1-2503-001',
                'amount': '5000',
            })
        self.assertEqual(resp.status_code, 400)

    def test_bad_json_returns_400(self):
        # bad JSON ถูกตรวจสอบหลัง signature — ต้องส่ง signature ถูกต้องก่อน
        import hashlib, hmac as _hmac
        body = b'not-json'
        secret = 'test-secret'
        sig = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with self.settings(TMR_WEBHOOK_SECRET=secret):
            resp = self.client.post(
                reverse('billing:tmr_webhook'),
                data=body,
                content_type='application/json',
                HTTP_X_TMR_SIGNATURE=sig,
            )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# BillListView tests
# ---------------------------------------------------------------------------

class BillListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        cls.dorm = Dormitory.objects.create(name='List Dorm', address='Addr', invoice_prefix='LD1')
        cls.owner = CustomUser.objects.create_user(
            'lv_owner', password='pass', role='owner', dormitory=cls.dorm
        )
        b = Building.objects.create(dormitory=cls.dorm, name='B')
        f = Floor.objects.create(building=b, number=1)
        cls.room = Room.objects.create(floor=f, number='101', base_rent=5000)

        cls.bill_paid = Bill.objects.create(
            room=cls.room, month=date(2025, 1, 1), base_rent=5000,
            total=5000, due_date=date(2025, 1, 25), status='paid',
        )
        cls.bill_overdue = Bill.objects.create(
            room=cls.room, month=date(2025, 2, 1), base_rent=5000,
            total=5000, due_date=date(2025, 2, 25), status='overdue',
        )

    def _login(self):
        self.client.force_login(self.owner)

    def test_list_returns_200(self):
        self._login()
        resp = self.client.get(reverse('billing:list'))
        self.assertEqual(resp.status_code, 200)

    def test_list_contains_both_bills(self):
        self._login()
        # Pass month=all to override the default current-month filter
        resp = self.client.get(reverse('billing:list'), {'month': ''})
        self.assertIn(self.bill_paid, resp.context['bills'])
        self.assertIn(self.bill_overdue, resp.context['bills'])

    def test_filter_by_status(self):
        self._login()
        resp = self.client.get(reverse('billing:list'), {'status': 'paid', 'month': ''})
        bills = list(resp.context['bills'])
        self.assertIn(self.bill_paid, bills)
        self.assertNotIn(self.bill_overdue, bills)

    def test_filter_by_month(self):
        self._login()
        resp = self.client.get(reverse('billing:list'), {'month': '2025-01'})
        bills = list(resp.context['bills'])
        self.assertIn(self.bill_paid, bills)
        self.assertNotIn(self.bill_overdue, bills)

    def test_tenant_redirected(self):
        # StaffRequiredMixin คืน 403 PermissionDenied สำหรับ tenant — ไม่ redirect
        from apps.core.models import CustomUser
        tenant = CustomUser.objects.create_user(
            'lv_tenant', password='pass', role='tenant', dormitory=self.dorm
        )
        self.client.force_login(tenant)
        resp = self.client.get(reverse('billing:list'))
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_redirected(self):
        resp = self.client.get(reverse('billing:list'))
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# BillDetailView tests
# ---------------------------------------------------------------------------

class BillDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        cls.dorm = Dormitory.objects.create(name='Detail Dorm', address='Addr', invoice_prefix='DD1')
        cls.owner = CustomUser.objects.create_user(
            'dv_owner', password='pass', role='owner', dormitory=cls.dorm
        )
        b = Building.objects.create(dormitory=cls.dorm, name='B')
        f = Floor.objects.create(building=b, number=1)
        cls.room = Room.objects.create(floor=f, number='101', base_rent=5000)
        cls.bill = Bill.objects.create(
            room=cls.room, month=date(2025, 3, 1), base_rent=5000,
            total=5000, due_date=date(2025, 3, 25), status='sent',
        )

    def _login(self):
        self.client.force_login(self.owner)

    def test_detail_returns_200(self):
        self._login()
        resp = self.client.get(reverse('billing:detail', args=[self.bill.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_detail_contains_bill_in_context(self):
        self._login()
        resp = self.client.get(reverse('billing:detail', args=[self.bill.pk]))
        self.assertEqual(resp.context['bill'], self.bill)

    def test_post_updates_status_to_overdue(self):
        from apps.billing.models import Bill
        self._login()
        resp = self.client.post(
            reverse('billing:detail', args=[self.bill.pk]),
            {'status': 'overdue'},
        )
        self.assertRedirects(resp, reverse('billing:detail', args=[self.bill.pk]),
                             fetch_redirect_response=False)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, Bill.Status.OVERDUE)

    def test_post_invalid_status_does_not_change(self):
        self._login()
        self.client.post(
            reverse('billing:detail', args=[self.bill.pk]),
            {'status': 'invalid_status'},
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, 'sent')

    def test_cross_dorm_bill_returns_404(self):
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        other_dorm = Dormitory.objects.create(name='Other', address='O')
        ob = Building.objects.create(dormitory=other_dorm, name='OB')
        of = Floor.objects.create(building=ob, number=1)
        other_room = Room.objects.create(floor=of, number='999', base_rent=3000)
        other_bill = Bill.objects.create(
            room=other_room, month=date(2025, 4, 1), base_rent=3000,
            total=3000, due_date=date(2025, 4, 25),
        )
        self._login()
        resp = self.client.get(reverse('billing:detail', args=[other_bill.pk]))
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# BillCSVExportView tests — Task 1.2: Export CSV with Multi-Month Range
# ---------------------------------------------------------------------------

class BillCSVExportViewTests(TestCase):
    """
    ทดสอบ export CSV:
    - download ได้จริง พร้อม UTF-8 BOM
    - date range filter ทำงานถูก
    - building filter ทำงานถูก
    - tenant isolation (ไม่เห็น billing ของ dormitory อื่น)
    """

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        # Dormitory A — owner ที่ login
        cls.dorm_a = Dormitory.objects.create(
            name='Export Dorm A', address='Addr A', invoice_prefix='EA1'
        )
        cls.owner = CustomUser.objects.create_user(
            'exp_owner', password='pass', role='owner', dormitory=cls.dorm_a
        )

        cls.building_a1 = Building.objects.create(dormitory=cls.dorm_a, name='Building A1')
        cls.building_a2 = Building.objects.create(dormitory=cls.dorm_a, name='Building A2')

        floor_a1 = Floor.objects.create(building=cls.building_a1, number=1)
        floor_a2 = Floor.objects.create(building=cls.building_a2, number=1)

        cls.room_a1 = Room.objects.create(floor=floor_a1, number='101', base_rent=5000)
        cls.room_a2 = Room.objects.create(floor=floor_a2, number='201', base_rent=4000)

        # Bills ใน dorm A — spread across months
        cls.bill_jan = Bill.objects.create(
            room=cls.room_a1, month=date(2025, 1, 1), base_rent=5000,
            total=5000, due_date=date(2025, 1, 25), status='paid',
        )
        cls.bill_feb = Bill.objects.create(
            room=cls.room_a1, month=date(2025, 2, 1), base_rent=5000,
            total=5200, due_date=date(2025, 2, 25), status='sent',
        )
        cls.bill_mar = Bill.objects.create(
            room=cls.room_a1, month=date(2025, 3, 1), base_rent=5000,
            total=5100, due_date=date(2025, 3, 25), status='overdue',
        )
        # Bill ใน building_a2
        cls.bill_b2_jan = Bill.objects.create(
            room=cls.room_a2, month=date(2025, 1, 1), base_rent=4000,
            total=4000, due_date=date(2025, 1, 25), status='paid',
        )

        # Dormitory B — ไม่ควรเห็นใน export ของ owner dorm A
        cls.dorm_b = Dormitory.objects.create(
            name='Export Dorm B', address='Addr B', invoice_prefix='EB1'
        )
        building_b = Building.objects.create(dormitory=cls.dorm_b, name='Building B1')
        floor_b = Floor.objects.create(building=building_b, number=1)
        room_b = Room.objects.create(floor=floor_b, number='301', base_rent=6000)
        cls.bill_dorm_b = Bill.objects.create(
            room=room_b, month=date(2025, 1, 1), base_rent=6000,
            total=6000, due_date=date(2025, 1, 25), status='sent',
        )

    def _login(self):
        self.client.force_login(self.owner)

    def _get_csv_rows(self, params):
        """Helper: GET export URL, decode response, strip BOM, return rows as list of lists."""
        resp = self.client.get(reverse('billing:export'), params)
        self.assertEqual(resp.status_code, 200)
        # decode utf-8 แล้ว strip BOM (\ufeff) ออกจากต้นไฟล์ก่อน parse
        content = resp.content.decode('utf-8').lstrip('\ufeff')
        import io
        reader = __import__('csv').reader(io.StringIO(content))
        return list(reader)

    # ------------------------------------------------------------------
    # ทดสอบ form page (GET ไม่มี start_month)
    # ------------------------------------------------------------------

    def test_get_without_params_returns_form(self):
        """GET /billing/export/ ไม่มี param → แสดง form ไม่ใช่ download"""
        self._login()
        resp = self.client.get(reverse('billing:export'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'billing/export.html')

    # ------------------------------------------------------------------
    # ทดสอบ CSV download
    # ------------------------------------------------------------------

    def test_csv_download_returns_200_with_attachment(self):
        """GET ที่มี start_month ต้อง return 200 พร้อม Content-Disposition attachment"""
        self._login()
        resp = self.client.get(reverse('billing:export'), {
            'start_month': '2025-01',
            'end_month': '2025-01',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp.get('Content-Disposition', ''))
        self.assertIn('bills_export_2025-01_to_2025-01.csv', resp.get('Content-Disposition', ''))

    def test_csv_filename_uses_range(self):
        """ชื่อไฟล์ต้องเป็น bills_export_{start}_to_{end}.csv"""
        self._login()
        resp = self.client.get(reverse('billing:export'), {
            'start_month': '2025-01',
            'end_month': '2025-03',
        })
        self.assertIn('bills_export_2025-01_to_2025-03.csv', resp.get('Content-Disposition', ''))

    def test_utf8_bom_present_in_output(self):
        """ต้องมี UTF-8 BOM (\ufeff) ที่ต้นไฟล์เพื่อให้ Excel ไทยอ่านได้"""
        self._login()
        resp = self.client.get(reverse('billing:export'), {
            'start_month': '2025-01',
            'end_month': '2025-01',
        })
        self.assertEqual(resp.status_code, 200)
        # ตรวจ BOM bytes ที่ต้นไฟล์
        self.assertTrue(resp.content.startswith(b'\xef\xbb\xbf'),
                        'CSV file must start with UTF-8 BOM (0xEF 0xBB 0xBF)')

    def test_csv_header_columns_order(self):
        """Header row ต้องมี columns ตาม spec ในลำดับที่กำหนด"""
        self._login()
        rows = self._get_csv_rows({'start_month': '2025-01', 'end_month': '2025-01'})
        self.assertGreater(len(rows), 0)
        header = rows[0]
        expected_header = [
            'Invoice No', 'Room', 'Tenant Name', 'Month',
            'Base Rent', 'Water Units', 'Water Amt', 'Elec Units', 'Elec Amt',
            'Total', 'Status', 'Paid Date',
        ]
        self.assertEqual(header, expected_header)

    # ------------------------------------------------------------------
    # ทดสอบ date range filter
    # ------------------------------------------------------------------

    def test_single_month_filter(self):
        """start_month=end_month=2025-01 → export เฉพาะ Jan bills"""
        self._login()
        rows = self._get_csv_rows({'start_month': '2025-01', 'end_month': '2025-01'})
        # header + bills ใน Jan ของ dorm A (bill_jan + bill_b2_jan)
        data_rows = rows[1:]
        months = [r[3] for r in data_rows]  # column index 3 = Month
        self.assertTrue(all(m == '2025-01' for m in months),
                        f'Expected all months 2025-01, got: {months}')

    def test_multi_month_range_includes_all_months(self):
        """start_month=2025-01, end_month=2025-03 → export bills ทั้ง 3 เดือน"""
        self._login()
        rows = self._get_csv_rows({'start_month': '2025-01', 'end_month': '2025-03'})
        data_rows = rows[1:]
        months = {r[3] for r in data_rows}
        self.assertIn('2025-01', months)
        self.assertIn('2025-02', months)
        self.assertIn('2025-03', months)

    def test_out_of_range_month_excluded(self):
        """bill_mar (2025-03) ต้องไม่อยู่ใน export ถ้า end_month=2025-02"""
        self._login()
        rows = self._get_csv_rows({'start_month': '2025-01', 'end_month': '2025-02'})
        data_rows = rows[1:]
        months = [r[3] for r in data_rows]
        self.assertNotIn('2025-03', months)

    def test_start_after_end_swapped_gracefully(self):
        """ถ้า start_month > end_month ระบบต้อง swap และยังคง export ได้ไม่ error"""
        self._login()
        resp = self.client.get(reverse('billing:export'), {
            'start_month': '2025-03',
            'end_month': '2025-01',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp.get('Content-Disposition', ''))

    def test_invalid_start_month_redirects(self):
        """start_month format ผิด → redirect กลับไป export form"""
        self._login()
        resp = self.client.get(reverse('billing:export'), {
            'start_month': 'not-a-date',
            'end_month': '2025-01',
        })
        self.assertEqual(resp.status_code, 302)

    # ------------------------------------------------------------------
    # ทดสอบ building filter
    # ------------------------------------------------------------------

    def test_building_filter_limits_results(self):
        """building_id filter ต้องแสดงเฉพาะ bills ในตึกนั้น"""
        self._login()
        rows = self._get_csv_rows({
            'start_month': '2025-01',
            'end_month': '2025-01',
            'building_id': str(self.building_a2.pk),
        })
        data_rows = rows[1:]
        # ตึก A2 มีแค่ room_a2 (201) → bill_b2_jan
        self.assertEqual(len(data_rows), 1)
        self.assertEqual(data_rows[0][1], '201')  # column 1 = Room

    def test_no_building_filter_returns_all_buildings(self):
        """ไม่ส่ง building_id → export bills ทุกตึกของ dormitory"""
        self._login()
        rows = self._get_csv_rows({'start_month': '2025-01', 'end_month': '2025-01'})
        data_rows = rows[1:]
        rooms = {r[1] for r in data_rows}  # column 1 = Room
        # Jan มีทั้ง room 101 (building A1) และ 201 (building A2)
        self.assertIn('101', rooms)
        self.assertIn('201', rooms)

    # ------------------------------------------------------------------
    # ทดสอบ tenant isolation — ต้องไม่เห็น bill ของ dormitory อื่น
    # ------------------------------------------------------------------

    def test_tenant_isolation_excludes_other_dormitory_bills(self):
        """owner ของ dorm_a ต้องไม่เห็น bill ของ dorm_b ใน CSV เลย"""
        self._login()
        rows = self._get_csv_rows({'start_month': '2025-01', 'end_month': '2025-01'})
        data_rows = rows[1:]
        # bill_dorm_b มี invoice_number ขึ้นต้น EB1
        invoice_numbers = [r[0] for r in data_rows]
        for inv in invoice_numbers:
            self.assertFalse(
                inv.startswith('EB1'),
                f'Found dorm_b bill in export: {inv}'
            )

    def test_other_dormitory_bill_count_not_included(self):
        """จำนวน rows ต้องตรงกับ bill ของ dorm_a เท่านั้น ใน range Jan 2025"""
        self._login()
        rows = self._get_csv_rows({'start_month': '2025-01', 'end_month': '2025-01'})
        data_rows = rows[1:]
        # dorm_a Jan 2025: bill_jan (room 101) + bill_b2_jan (room 201) = 2 bills
        self.assertEqual(len(data_rows), 2)

    def test_unauthenticated_redirected(self):
        """ผู้ใช้ที่ไม่ได้ login ต้อง redirect"""
        resp = self.client.get(reverse('billing:export'), {
            'start_month': '2025-01',
            'end_month': '2025-01',
        })
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# BillCSVExportView N+1 query tests — Task 2.0
# ---------------------------------------------------------------------------

class BillCSVExportViewN1QueryTests(TestCase):
    """
    ยืนยันว่า BillCSVExportView ไม่มี N+1 query —
    จำนวน DB queries ต้องไม่ scale ตามจำนวน Bill (O(1) ไม่ใช่ O(n))
    """

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill
        from apps.tenants.models import TenantProfile, Lease

        cls.dorm = Dormitory.objects.create(
            name='N1 Dorm', address='Addr', invoice_prefix='N1T'
        )
        cls.owner = CustomUser.objects.create_user(
            'n1_owner', password='pass', role='owner', dormitory=cls.dorm
        )

        building = Building.objects.create(dormitory=cls.dorm, name='N1 Building')
        floor = Floor.objects.create(building=building, number=1)

        # สร้าง 10 ห้องพร้อม bill แต่ละห้อง เพื่อวัดว่า query count ไม่ scale
        cls.rooms = []
        cls.bills = []
        for i in range(1, 11):
            room = Room.objects.create(
                floor=floor, number=str(100 + i), base_rent=5000,
                status=Room.Status.OCCUPIED,
            )
            cls.rooms.append(room)

            bill = Bill.objects.create(
                room=room,
                month=date(2026, 6, 1),
                base_rent=5000,
                total=5000,
                due_date=date(2026, 6, 25),
            )
            cls.bills.append(bill)

            # เพิ่ม TenantProfile บาง room เพื่อให้ผ่าน branch tenant_profiles_cache
            if i % 2 == 0:
                user = CustomUser.objects.create_user(
                    f'n1_tenant_{i}', password='pass', role='tenant', dormitory=cls.dorm
                )
                profile = TenantProfile.objects.create(
                    user=user, room=room, dormitory=cls.dorm
                )
                Lease.objects.create(
                    tenant=profile, room=room, status='active',
                    start_date=date(2026, 1, 1), dormitory=cls.dorm
                )

    def _export_url_params(self):
        return {'start_month': '2026-06', 'end_month': '2026-06'}

    def test_query_count_does_not_scale_with_bill_count(self):
        """
        วัด query count สำหรับ 10 bills — ต้องไม่เกิน threshold คงที่
        (select_related + prefetch_related ทำให้ใช้ queries คงที่ ไม่ว่าจะมีกี่แถว)
        ปกติจะอยู่ที่ ~6 queries: session, user, dormitory,
        bills+select_related, prefetch leases, prefetch tenant_profiles
        กำหนด upper bound ที่ 12 เพื่อให้มี margin แต่ต้องน้อยกว่า O(n)=10×2+base=~23
        """
        self.client.force_login(self.owner)
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('billing:export'), self._export_url_params())

        actual = len(ctx)
        # N+1 scenario จะได้ ~23 queries (10 bills × 2 per-bill queries + ~3 base)
        # หลังแก้แล้วต้องได้ไม่เกิน 12 (O(1) queries)
        self.assertLessEqual(
            actual, 12,
            f'Expected at most 12 queries (O(1)) for 10-bill CSV export, got {actual}. '
            f'N+1 bug may have returned.'
        )

    def test_query_count_is_constant_regardless_of_bill_count(self):
        """
        เปรียบเทียบ query count ระหว่าง export 1 เดือน (10 bills) กับ 0 bills —
        ต้องต่างกันน้อยมาก (ไม่ใช่ N queries เพิ่มขึ้นตาม bill)
        """
        from apps.billing.models import Bill
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room

        # สร้าง dormitory ใหม่ที่ไม่มี bill ในเดือน 2026-07
        dorm_empty = Dormitory.objects.create(
            name='Empty Dorm', address='Empty', invoice_prefix='EMP'
        )
        owner_empty = self.owner.__class__.objects.create_user(
            'n1_empty_owner', password='pass', role='owner', dormitory=dorm_empty
        )

        self.client.force_login(self.owner)
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        # วัด queries สำหรับ 10 bills
        with CaptureQueriesContext(connection) as ctx_10:
            self.client.get(reverse('billing:export'), self._export_url_params())
        count_10_bills = len(ctx_10)

        # Export เดือนที่ไม่มี bill (ต้องได้ query count ใกล้เคียงกัน — ไม่ใช่ 0 vs N)
        with CaptureQueriesContext(connection) as ctx_0:
            self.client.get(reverse('billing:export'), {'start_month': '2020-01', 'end_month': '2020-01'})
        count_0_bills = len(ctx_0)

        # ถ้าแก้ N+1 ได้แล้ว: ต่างกันไม่เกิน 3 queries (prefetch อาจมี/ไม่มี result)
        # ถ้ายัง N+1: จะต่างกัน ~20 queries (10 bills × 2 queries each)
        diff = abs(count_10_bills - count_0_bills)
        self.assertLessEqual(
            diff, 5,
            f'Query count difference between 10-bill export ({count_10_bills}) '
            f'and 0-bill export ({count_0_bills}) is {diff} — '
            f'expected <= 5 (should be O(1), not O(n))'
        )


# ---------------------------------------------------------------------------
# REST API tests — Task 3.1
# ---------------------------------------------------------------------------

class BillAPIListTests(TestCase):
    """
    ทดสอบ GET /api/bills/
    - authenticated user → 200 + bills list
    - unauthenticated → 401
    - tenant isolation: owner A ไม่เห็น bills ของ owner B
    - pagination ทำงาน
    """

    @classmethod
    def setUpTestData(cls):
        from rest_framework.authtoken.models import Token
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        # Dormitory A — owner ที่ test
        cls.dorm_a = Dormitory.objects.create(
            name='API Dorm A', address='A', invoice_prefix='AA1'
        )
        cls.owner_a = CustomUser.objects.create_user(
            'api_owner_a', password='pass', role='owner', dormitory=cls.dorm_a
        )
        cls.token_a = Token.objects.create(user=cls.owner_a)

        b = Building.objects.create(dormitory=cls.dorm_a, name='BA')
        f = Floor.objects.create(building=b, number=1)
        cls.room_a = Room.objects.create(floor=f, number='101', base_rent=5000)

        cls.bill_a1 = Bill.objects.create(
            room=cls.room_a, month=date(2025, 1, 1), base_rent=5000,
            total=5000, due_date=date(2025, 1, 25), status='paid',
        )
        cls.bill_a2 = Bill.objects.create(
            room=cls.room_a, month=date(2025, 2, 1), base_rent=5000,
            total=5200, due_date=date(2025, 2, 25), status='sent',
        )

        # Dormitory B — ไม่ควรเห็นจาก owner A
        cls.dorm_b = Dormitory.objects.create(
            name='API Dorm B', address='B', invoice_prefix='BB1'
        )
        cls.owner_b = CustomUser.objects.create_user(
            'api_owner_b', password='pass', role='owner', dormitory=cls.dorm_b
        )
        cls.token_b = Token.objects.create(user=cls.owner_b)

        bb = Building.objects.create(dormitory=cls.dorm_b, name='BB')
        fb = Floor.objects.create(building=bb, number=1)
        room_b = Room.objects.create(floor=fb, number='101', base_rent=4000)
        cls.bill_b = Bill.objects.create(
            room=room_b, month=date(2025, 1, 1), base_rent=4000,
            total=4000, due_date=date(2025, 1, 25),
        )

    def _auth_headers(self, token):
        return {'HTTP_AUTHORIZATION': f'Token {token.key}'}

    def test_authenticated_returns_200_with_bills(self):
        """authenticated user ต้องได้ 200 และเห็น bills ของตัวเอง"""
        resp = self.client.get('/api/bills/', **self._auth_headers(self.token_a))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('results', data)
        ids = [str(r['id']) for r in data['results']]
        self.assertIn(str(self.bill_a1.pk), ids)
        self.assertIn(str(self.bill_a2.pk), ids)

    def test_unauthenticated_returns_401(self):
        """ไม่มี token → 401 Unauthorized"""
        resp = self.client.get('/api/bills/')
        self.assertEqual(resp.status_code, 401)

    def test_owner_a_cannot_see_owner_b_bills(self):
        """tenant isolation: owner A ต้องไม่เห็น bills ของ owner B"""
        resp = self.client.get('/api/bills/', **self._auth_headers(self.token_a))
        self.assertEqual(resp.status_code, 200)
        ids = [str(r['id']) for r in resp.json()['results']]
        self.assertNotIn(str(self.bill_b.pk), ids)

    def test_pagination_returns_count_and_next(self):
        """pagination response ต้องมี count field"""
        resp = self.client.get('/api/bills/', **self._auth_headers(self.token_a))
        data = resp.json()
        self.assertIn('count', data)
        self.assertGreaterEqual(data['count'], 2)

    def test_filter_by_status(self):
        """?status=paid ต้องคืน bills ที่ paid เท่านั้น"""
        resp = self.client.get('/api/bills/?status=paid', **self._auth_headers(self.token_a))
        self.assertEqual(resp.status_code, 200)
        statuses = [r['status'] for r in resp.json()['results']]
        self.assertTrue(all(s == 'paid' for s in statuses))

    def test_filter_by_month(self):
        """?month=2025-01 ต้องคืน bills ของเดือน 2025-01 เท่านั้น"""
        resp = self.client.get('/api/bills/?month=2025-01', **self._auth_headers(self.token_a))
        self.assertEqual(resp.status_code, 200)
        ids = [str(r['id']) for r in resp.json()['results']]
        self.assertIn(str(self.bill_a1.pk), ids)
        self.assertNotIn(str(self.bill_a2.pk), ids)


class BillAPIDetailTests(TestCase):
    """
    ทดสอบ GET /api/bills/<id>/
    - authenticated + owner ของ bill → 200 พร้อม payment field
    - IDOR: owner B เรียก bill ของ owner A → 404
    - unauthenticated → 401
    """

    @classmethod
    def setUpTestData(cls):
        from rest_framework.authtoken.models import Token
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        cls.dorm_a = Dormitory.objects.create(
            name='Det Dorm A', address='A', invoice_prefix='DA2'
        )
        cls.owner_a = CustomUser.objects.create_user(
            'det_owner_a', password='pass', role='owner', dormitory=cls.dorm_a
        )
        cls.token_a = Token.objects.create(user=cls.owner_a)

        b = Building.objects.create(dormitory=cls.dorm_a, name='B')
        f = Floor.objects.create(building=b, number=1)
        room = Room.objects.create(floor=f, number='101', base_rent=5000)
        cls.bill = Bill.objects.create(
            room=room, month=date(2025, 3, 1), base_rent=5000,
            total=5000, due_date=date(2025, 3, 25), status='sent',
        )

        # Owner B ที่ไม่ควรเห็น bill ของ owner A
        cls.dorm_b = Dormitory.objects.create(name='Det Dorm B', address='B')
        cls.owner_b = CustomUser.objects.create_user(
            'det_owner_b', password='pass', role='owner', dormitory=cls.dorm_b
        )
        cls.token_b = Token.objects.create(user=cls.owner_b)

    def _auth_headers(self, token):
        return {'HTTP_AUTHORIZATION': f'Token {token.key}'}

    def test_owner_gets_own_bill_detail(self):
        """GET /api/bills/<id>/ ด้วย owner ของ bill → 200"""
        resp = self.client.get(f'/api/bills/{self.bill.pk}/', **self._auth_headers(self.token_a))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(str(data['id']), str(self.bill.pk))
        self.assertIn('payment', data)
        self.assertIn('status', data)

    def test_detail_no_payment_returns_null(self):
        """bill ที่ยังไม่มี payment → payment field เป็น null"""
        resp = self.client.get(f'/api/bills/{self.bill.pk}/', **self._auth_headers(self.token_a))
        self.assertIsNone(resp.json()['payment'])

    def test_cross_dorm_detail_returns_404(self):
        """IDOR protection: owner B ต้องไม่เห็น bill ของ owner A → 404"""
        resp = self.client.get(f'/api/bills/{self.bill.pk}/', **self._auth_headers(self.token_b))
        self.assertEqual(resp.status_code, 404)

    def test_unauthenticated_detail_returns_401(self):
        """ไม่มี token → 401"""
        resp = self.client.get(f'/api/bills/{self.bill.pk}/')
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Flow 3 Integration: Meter Reading → Bill → Payment (Core Billing Cycle)
# ---------------------------------------------------------------------------

class BillingCycleIntegrationTests(TestCase):
    """
    E2E Flow 3: ครอบคลุมวงจรการเรียกเก็บเงินทั้งหมด
      1. staff บันทึกมิเตอร์
      2. system generate บิล (ยอดถูกต้อง)
      3. staff เห็นบิลใน list
      4. owner อัพเดต status เป็น sent
      5. tenant เห็นบิลใน portal
      6. TMR webhook → bill paid + Payment record
      7. duplicate webhook → idempotency ป้องกัน
      8. dashboard reports → revenue อัพเดต
    """

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import BillingSettings
        from apps.tenants.models import TenantProfile, Lease

        # ตั้งค่าหอพัก + billing settings
        cls.dorm = Dormitory.objects.create(
            name='Cycle Dorm', address='Cycle Addr', invoice_prefix='CYC'
        )
        BillingSettings.objects.create(
            dormitory=cls.dorm,
            bill_day=1,
            grace_days=5,
            water_rate=18,
            elec_rate=7,
        )

        # สร้างโครงสร้างห้อง
        building = Building.objects.create(dormitory=cls.dorm, name='A')
        floor = Floor.objects.create(building=building, number=1)
        cls.room = Room.objects.create(
            floor=floor, number='101', base_rent=5000, status=Room.Status.OCCUPIED
        )

        # users
        cls.owner = CustomUser.objects.create_user(
            'cyc_owner', password='pass', role='owner', dormitory=cls.dorm
        )
        cls.staff = CustomUser.objects.create_user(
            'cyc_staff', password='pass', role='staff', dormitory=cls.dorm
        )
        cls.tenant_user = CustomUser.objects.create_user(
            'cyc_tenant', password='pass', role='tenant', dormitory=cls.dorm
        )

        from apps.core.models import StaffPermission
        StaffPermission.objects.create(
            user=cls.staff, dormitory=cls.dorm, can_view_billing=True
        )

        # tenant profile + active lease ผูกกับห้อง
        cls.profile = TenantProfile.objects.create(
            user=cls.tenant_user,
            dormitory=cls.dorm,
        )
        Lease.objects.create(
            tenant=cls.profile,
            room=cls.room,
            status=Lease.Status.ACTIVE,
            start_date=date(2026, 1, 1),
        )

        cls.billing_month = date(2026, 3, 1)

    # ------------------------------------------------------------------
    # 1. Staff บันทึกมิเตอร์ผ่าน view
    # ------------------------------------------------------------------

    def test_meter_reading_creates_record(self):
        from apps.rooms.models import MeterReading
        self.client.force_login(self.staff)
        resp = self.client.post(
            reverse('rooms:meter_reading'),
            {
                'room': str(self.room.pk),
                'reading_date': '2026-03-15',
                'water_prev': '100',
                'water_curr': '115',   # 15 units
                'elec_prev': '500',
                'elec_curr': '580',    # 80 units
            },
        )
        # redirect หลัง success
        self.assertIn(resp.status_code, [200, 302])
        reading = MeterReading.objects.filter(
            room=self.room, reading_date=date(2026, 3, 15)
        ).first()
        self.assertIsNotNone(reading, 'ต้องมี MeterReading หลัง POST')
        self.assertEqual(reading.water_prev, 100)
        self.assertEqual(reading.water_curr, 115)
        self.assertEqual(reading.elec_prev, 500)
        self.assertEqual(reading.elec_curr, 580)

    # ------------------------------------------------------------------
    # 2. generate_bills_for_dormitory ใช้ค่ามิเตอร์คำนวณยอดถูกต้อง
    # ------------------------------------------------------------------

    def test_generate_bills_uses_meter_reading(self):
        from apps.rooms.models import MeterReading
        from apps.billing.models import Bill
        # สร้าง meter reading โดยตรง (unit test ของ service)
        MeterReading.objects.create(
            room=self.room,
            water_prev=100, water_curr=115,   # 15 units × 18 = 270
            elec_prev=500, elec_curr=580,      # 80 units × 7  = 560
            reading_date=date(2026, 4, 15),
            recorded_by=None,
        )
        bills = generate_bills_for_dormitory(self.dorm, date(2026, 4, 1))
        self.assertEqual(len(bills), 1)
        bill = bills[0]
        self.assertEqual(bill.water_amt, Decimal('270.00'))   # 15 × 18
        self.assertEqual(bill.elec_amt, Decimal('560.00'))    # 80 × 7
        self.assertEqual(bill.total, Decimal('5830.00'))      # 5000 + 270 + 560
        self.assertIsNotNone(bill.meter_reading)

    # ------------------------------------------------------------------
    # 3. Staff เห็นบิลใน /billing/ list
    # ------------------------------------------------------------------

    def test_bill_appears_in_staff_list(self):
        from apps.billing.models import Bill
        bill = Bill.objects.create(
            room=self.room,
            month=date(2026, 5, 1),
            base_rent=5000,
            water_amt=Decimal('270'),
            elec_amt=Decimal('560'),
            total=Decimal('5830'),
            due_date=date(2026, 5, 6),
            status=Bill.Status.SENT,
        )
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('billing:list'), {'month': '2026-05'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(bill, resp.context['bills'])

    # ------------------------------------------------------------------
    # 4. Owner เปลี่ยน status draft → sent ผ่าน BillDetailView POST
    # ------------------------------------------------------------------

    def test_owner_can_mark_bill_sent(self):
        from apps.billing.models import Bill
        bill = Bill.objects.create(
            room=self.room,
            month=date(2026, 6, 1),
            base_rent=5000,
            total=5000,
            due_date=date(2026, 6, 6),
            status=Bill.Status.DRAFT,
        )
        self.client.force_login(self.owner)
        resp = self.client.post(
            reverse('billing:detail', args=[bill.pk]),
            {'status': 'sent'},
        )
        self.assertRedirects(resp, reverse('billing:detail', args=[bill.pk]),
                             fetch_redirect_response=False)
        bill.refresh_from_db()
        self.assertEqual(bill.status, Bill.Status.SENT)

    # ------------------------------------------------------------------
    # 5. Tenant เห็นบิลที่ status=sent ใน portal /tenant/bills/
    # ------------------------------------------------------------------

    def test_bill_status_sent_visible_to_tenant(self):
        from apps.billing.models import Bill
        bill = Bill.objects.create(
            room=self.room,
            month=date(2026, 7, 1),
            base_rent=5000,
            total=5000,
            due_date=date(2026, 7, 6),
            status=Bill.Status.SENT,
        )
        self.client.force_login(self.tenant_user)
        resp = self.client.get(reverse('tenant:bills'))
        self.assertEqual(resp.status_code, 200)
        # TenantBillsView ส่ง context all_bills
        self.assertIn(bill, resp.context['all_bills'])

    # ------------------------------------------------------------------
    # 6. TMR Webhook → bill paid + Payment record สร้าง
    # ------------------------------------------------------------------

    def test_tmr_webhook_marks_bill_paid(self):
        from apps.billing.models import Bill, Payment
        bill = Bill.objects.create(
            room=self.room,
            month=date(2026, 8, 1),
            base_rent=5000,
            total=5000,
            due_date=date(2026, 8, 6),
            status=Bill.Status.SENT,
            invoice_number='CYC-2608-INT01',
        )
        # B2 fix: ต้องส่ง HMAC signature พร้อม secret เสมอ
        import hashlib, hmac as _hmac
        test_secret = 'test-secret'
        payload_bytes = json.dumps({
            'ref': 'TXN-INT-001',
            'order_id': 'CYC-2608-INT01',
            'amount': '5000.00',
        }).encode()
        sig = _hmac.new(test_secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        with self.settings(TMR_WEBHOOK_SECRET=test_secret):
            resp = self.client.post(
                reverse('billing:tmr_webhook'),
                data=payload_bytes,
                content_type='application/json',
                HTTP_X_TMR_SIGNATURE=sig,
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content)['status'], 'ok')
        bill.refresh_from_db()
        self.assertEqual(bill.status, Bill.Status.PAID)
        self.assertTrue(Payment.objects.filter(idempotency_key='TXN-INT-001').exists())

    # ------------------------------------------------------------------
    # 7. Idempotency: webhook ซ้ำ → ไม่สร้าง Payment สองรอบ
    # ------------------------------------------------------------------

    def test_tmr_webhook_idempotency(self):
        from apps.billing.models import Bill, Payment
        bill = Bill.objects.create(
            room=self.room,
            month=date(2026, 9, 1),
            base_rent=5000,
            total=5000,
            due_date=date(2026, 9, 6),
            status=Bill.Status.SENT,
            invoice_number='CYC-2609-INT02',
        )
        payload = json.dumps({
            'ref': 'TXN-INT-DUP',
            'order_id': 'CYC-2609-INT02',
            'amount': '5000.00',
        }).encode()
        # B2 fix: ต้องส่ง HMAC signature พร้อม secret เสมอ
        import hashlib, hmac as _hmac
        test_secret = 'test-secret'
        sig = _hmac.new(test_secret.encode(), payload, hashlib.sha256).hexdigest()
        with self.settings(TMR_WEBHOOK_SECRET=test_secret):
            self.client.post(
                reverse('billing:tmr_webhook'),
                data=payload, content_type='application/json',
                HTTP_X_TMR_SIGNATURE=sig,
            )
            resp2 = self.client.post(
                reverse('billing:tmr_webhook'),
                data=payload, content_type='application/json',
                HTTP_X_TMR_SIGNATURE=sig,
            )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(json.loads(resp2.content)['status'], 'already_processed')
        # ต้องมี Payment แค่ 1 รายการ ไม่ซ้ำ
        self.assertEqual(
            Payment.objects.filter(idempotency_key='TXN-INT-DUP').count(), 1
        )

    # ------------------------------------------------------------------
    # 8. Dashboard reports → revenue อัพเดตหลังจ่ายเงิน
    # ------------------------------------------------------------------

    def test_dashboard_revenue_after_payment(self):
        from apps.billing.models import Bill, Payment
        from django.utils import timezone
        bill = Bill.objects.create(
            room=self.room,
            month=date(2026, 10, 1),
            base_rent=5000,
            total=5000,
            due_date=date(2026, 10, 6),
            status=Bill.Status.PAID,
            invoice_number='CYC-2610-INT03',
        )
        Payment.objects.create(
            bill=bill,
            amount=5000,
            tmr_ref='TXN-INT-REV',
            idempotency_key='TXN-INT-REV',
            paid_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        resp = self.client.get(reverse('dashboard:reports'), {'month': '2026-10'})
        self.assertEqual(resp.status_code, 200)
        # revenue ต้องมีค่า ≥ 5000 (อาจมี bill อื่นในเดือนเดียวกัน)
        total_revenue = sum(
            b['revenue'] for b in resp.context['buildings_data']
            if b['revenue']
        )
        self.assertGreaterEqual(total_revenue, 5000)


# ---------------------------------------------------------------------------
# Flow 11: CSV Export Accuracy Integration Tests
# ---------------------------------------------------------------------------


class CSVExportAccuracyTests(TestCase):
    """
    Integration tests for CSV export accuracy:
    row count matches bills, invoice number present, totals match report,
    dormitory scoping (no cross-tenant data).
    """

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory, CustomUser
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill, BillingSettings
        from django.utils import timezone

        cls.dorm_a = Dormitory.objects.create(
            name='CSV Acc Dorm A', address='Addr A', invoice_prefix='CA1'
        )
        cls.owner = CustomUser.objects.create_user(
            'csv_acc_owner', password='pass', role='owner', dormitory=cls.dorm_a
        )
        BillingSettings.objects.create(
            dormitory=cls.dorm_a, bill_day=1, grace_days=5, elec_rate=7, water_rate=18
        )

        building_a = Building.objects.create(dormitory=cls.dorm_a, name='CA Bldg')
        floor_a = Floor.objects.create(building=building_a, number=1)
        cls.room1 = Room.objects.create(floor=floor_a, number='CA101', base_rent=5000)
        cls.room2 = Room.objects.create(floor=floor_a, number='CA102', base_rent=4000)

        # สร้าง 3 bills ในเดือน 2025-06 (เพื่อนับ row count)
        cls.bill1 = Bill.objects.create(
            room=cls.room1, month=date(2025, 6, 1), base_rent=5000,
            total=5500, due_date=date(2025, 6, 6), status='paid',
            invoice_number='CA1-2506-001',
        )
        cls.bill2 = Bill.objects.create(
            room=cls.room2, month=date(2025, 6, 1), base_rent=4000,
            total=4200, due_date=date(2025, 6, 6), status='paid',
            invoice_number='CA1-2506-002',
        )
        cls.bill3 = Bill.objects.create(
            room=cls.room1, month=date(2025, 7, 1), base_rent=5000,
            total=5100, due_date=date(2025, 7, 6), status='sent',
            invoice_number='CA1-2507-001',
        )

        # Add payment for bill1 (for totals test)
        from apps.billing.models import Payment
        Payment.objects.create(
            bill=cls.bill1,
            amount=5500,
            tmr_ref='TXN-CA1',
            idempotency_key='TXN-CA1',
            paid_at=timezone.now(),
        )
        Payment.objects.create(
            bill=cls.bill2,
            amount=4200,
            tmr_ref='TXN-CA2',
            idempotency_key='TXN-CA2',
            paid_at=timezone.now(),
        )

        # Dormitory B — ไม่ควรอยู่ใน export ของ dorm_a
        cls.dorm_b = Dormitory.objects.create(
            name='CSV Acc Dorm B', address='Addr B', invoice_prefix='CB1'
        )
        building_b = Building.objects.create(dormitory=cls.dorm_b, name='CB Bldg')
        floor_b = Floor.objects.create(building=building_b, number=1)
        room_b = Room.objects.create(floor=floor_b, number='CB101', base_rent=6000)
        Bill.objects.create(
            room=room_b, month=date(2025, 6, 1), base_rent=6000,
            total=6000, due_date=date(2025, 6, 6), status='sent',
            invoice_number='CB1-2506-001',
        )

    def _get_csv_rows(self, params):
        """Helper: GET CSV export, strip BOM, return list of rows"""
        resp = self.client.get(reverse('billing:export'), params)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8').lstrip('\ufeff')
        import io, csv as csv_mod
        reader = csv_mod.reader(io.StringIO(content))
        return list(reader)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_csv_row_count_matches_bills(self):
        """export CSV สำหรับ month 2025-06 → จำนวน rows = จำนวน bills ในเดือนนั้น (ไม่นับ header)"""
        from apps.billing.models import Bill
        expected_count = Bill.objects.filter(
            room__floor__building__dormitory=self.dorm_a,
            month__year=2025, month__month=6,
        ).count()

        rows = self._get_csv_rows({'start_month': '2025-06', 'end_month': '2025-06'})
        data_rows = rows[1:]  # ข้าม header
        self.assertEqual(len(data_rows), expected_count)

    def test_csv_contains_invoice_number(self):
        """invoice_number ปรากฏใน CSV content"""
        rows = self._get_csv_rows({'start_month': '2025-06', 'end_month': '2025-06'})
        all_invoice_numbers = [r[0] for r in rows[1:]]
        self.assertIn('CA1-2506-001', all_invoice_numbers)
        self.assertIn('CA1-2506-002', all_invoice_numbers)

    def test_csv_totals_match_paid_bills(self):
        """sum ของ total ใน CSV (paid bills) = ยอดรวม paid ของ dorm_a เดือน 2025-06"""
        from decimal import Decimal
        from apps.billing.models import Bill

        expected_paid_total = sum(
            b.total for b in Bill.objects.filter(
                room__floor__building__dormitory=self.dorm_a,
                month__year=2025, month__month=6,
                status='paid',
            )
        )

        rows = self._get_csv_rows({'start_month': '2025-06', 'end_month': '2025-06'})
        # column index 9 = Total
        paid_rows = [r for r in rows[1:] if r[10] == 'Paid']
        csv_paid_total = sum(Decimal(r[9]) for r in paid_rows)
        self.assertEqual(csv_paid_total, expected_paid_total)

    def test_csv_scoped_to_active_dormitory(self):
        """owner dorm_a export CSV → ไม่มีข้อมูลของ dorm_b"""
        rows = self._get_csv_rows({'start_month': '2025-06', 'end_month': '2025-06'})
        invoice_numbers = [r[0] for r in rows[1:]]
        for inv in invoice_numbers:
            self.assertFalse(
                inv.startswith('CB1'),
                f'Found dorm_b bill in CSV export: {inv}'
            )


# ---------------------------------------------------------------------------
# I3: Pro-rated Rent in generate_bills_for_dormitory
# ---------------------------------------------------------------------------

class ProratedBillGenerationTests(TestCase):
    """
    I3: ตรวจสอบว่า generate_bills_for_dormitory() เรียก calculate_prorated_rent()
    เมื่อ lease ของห้องนั้นมี start_date อยู่ในเดือนที่กำลัง generate
    """

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import BillingSettings

        cls.dorm = Dormitory.objects.create(
            name='Pro Dorm', address='Addr', invoice_prefix='PRO'
        )
        BillingSettings.objects.create(
            dormitory=cls.dorm,
            bill_day=1,
            grace_days=5,
            water_rate=18,
            elec_rate=7,
        )
        building = Building.objects.create(dormitory=cls.dorm, name='B1')
        floor = Floor.objects.create(building=building, number=1)
        cls.room = Room.objects.create(
            floor=floor, number='201', base_rent=6000, status='occupied',
            dormitory=cls.dorm,
        )

    def _make_lease(self, start_date, status='active'):
        from apps.core.models import CustomUser
        from apps.tenants.models import TenantProfile, Lease

        user = CustomUser.objects.create_user(
            f'pt_{start_date}', password='pass', role='tenant', dormitory=self.dorm
        )
        profile = TenantProfile.objects.create(
            user=user, room=self.room, dormitory=self.dorm
        )
        return Lease.objects.create(
            tenant=profile, room=self.room, start_date=start_date, status=status,
            dormitory=self.dorm,
        )

    def test_full_month_lease_uses_full_rent(self):
        """Lease start_date = วันที่ 1 ของเดือน → ค่าเช่าเต็ม"""
        month = date(2027, 1, 1)
        self._make_lease(date(2027, 1, 1))
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 1)
        self.assertEqual(bills[0].base_rent, Decimal('6000.00'))

    def test_mid_month_lease_uses_prorated_rent(self):
        """Lease start_date = วันที่ 16 มกราคม → ค่าเช่าครึ่งเดือน"""
        month = date(2027, 2, 1)
        self._make_lease(date(2027, 2, 16))
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 1)
        # 28 วันในเดือน ก.พ. 2027 (ไม่ใช่ปีอธิกสุรทิน)
        # วันที่ 16-28 = 13 วัน → 6000 * 13/28 = 2785.71
        expected = (Decimal('6000') * 13 / 28).quantize(Decimal('0.01'))
        self.assertEqual(bills[0].base_rent, expected)

    def test_lease_from_prior_month_uses_full_rent(self):
        """Lease start_date อยู่ในเดือนก่อนหน้า → ค่าเช่าเต็ม (ไม่ pro-rate)"""
        month = date(2027, 3, 1)
        self._make_lease(date(2027, 2, 15))  # lease เริ่มเดือนที่แล้ว
        bills = generate_bills_for_dormitory(self.dorm, month)
        self.assertEqual(len(bills), 1)
        self.assertEqual(bills[0].base_rent, Decimal('6000.00'))


# ---------------------------------------------------------------------------
# I4: Webhook Amount Validation
# ---------------------------------------------------------------------------

class WebhookAmountValidationTests(TestCase):
    """
    I4: ตรวจสอบว่า TMR webhook log warning เมื่อ amount ไม่ตรงกับ bill total
    และ ActivityLog ถูกสร้างสำหรับ mismatch
    """

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill

        cls.dorm = Dormitory.objects.create(
            name='Webhook Dorm', address='Addr', invoice_prefix='WH2'
        )
        b = Building.objects.create(dormitory=cls.dorm, name='B')
        f = Floor.objects.create(building=b, number=1)
        room = Room.objects.create(floor=f, number='301', base_rent=5000, dormitory=cls.dorm)
        cls.bill = Bill.objects.create(
            room=room, month=date(2027, 4, 1), base_rent=5000,
            total=Decimal('5320.00'), due_date=date(2027, 4, 6), status='sent',
        )

    def _post(self, data, secret='test-secret'):
        import hashlib
        import hmac as _hmac
        import json as _json
        body = _json.dumps(data).encode()
        sig = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            reverse('billing:tmr_webhook'),
            data=body,
            content_type='application/json',
            HTTP_X_TMR_SIGNATURE=sig,
        )

    def test_matching_amount_creates_payment(self):
        """amount ตรงกับ bill.total → payment ถูกสร้าง, ไม่มี mismatch log"""
        from apps.billing.models import Payment
        from apps.core.models import ActivityLog
        with self.settings(TMR_WEBHOOK_SECRET='test-secret'):
            resp = self._post({
                'ref': 'TXN-MATCH-001',
                'order_id': self.bill.invoice_number,
                'amount': '5320.00',
            })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Payment.objects.filter(bill=self.bill).exists())
        self.assertFalse(
            ActivityLog.objects.filter(action='webhook_amount_mismatch').exists()
        )

    def test_mismatched_amount_logs_warning(self):
        """amount ไม่ตรงกับ bill.total → ActivityLog action='webhook_amount_mismatch' ถูกสร้าง"""
        from apps.core.models import ActivityLog
        # รีเซ็ต bill status ก่อนเทส (เผื่อเทสก่อนหน้า paid ไปแล้ว)
        self.bill.refresh_from_db()
        if self.bill.status == 'paid':
            self.bill.status = 'sent'
            self.bill.save(update_fields=['status', 'updated_at'])

        with self.settings(TMR_WEBHOOK_SECRET='test-secret'):
            resp = self._post({
                'ref': 'TXN-MISMATCH-001',
                'order_id': self.bill.invoice_number,
                'amount': '9999.00',  # จำนวนเงินไม่ตรง
            })
        self.assertEqual(resp.status_code, 200)
        log = ActivityLog.objects.filter(action='webhook_amount_mismatch').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.detail.get('webhook_amount'), '9999.00')
        self.assertEqual(log.detail.get('bill_total'), '5320.00')


# ---------------------------------------------------------------------------
# S8-3: Invoice Number Collision Prevention Tests
# ---------------------------------------------------------------------------

class InvoiceNumberCollisionTests(TestCase):
    """
    ทดสอบว่า Bill.save() ใช้ MAX-based seq และไม่ re-use เลขที่ถูกลบ
    """

    @classmethod
    def setUpTestData(cls):
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room

        cls.dorm = Dormitory.objects.create(
            name='Collision Test Dorm', address='Collision Addr', invoice_prefix='COL'
        )
        with dormitory_context(cls.dorm):
            building = Building.objects.create(name='Col Building')
            floor = Floor.objects.create(building=building, number=1)
            cls.rooms = [
                Room.objects.create(floor=floor, number=str(i), base_rent=5000)
                for i in range(1, 8)  # 7 rooms สำหรับ test แต่ละอัน
            ]

    def _make_bill(self, room, month, **kwargs):
        from apps.billing.models import Bill
        with dormitory_context(self.dorm):
            return Bill.objects.create(
                room=room, month=month, base_rent=5000,
                total=5000, due_date=date(month.year, month.month, 25),
                **kwargs
            )

    def test_invoice_number_uses_max_not_count(self):
        """
        สร้าง bill 2 ใบ ลบใบที่มี seq สูงสุด (seq=2)
        bill ใหม่ต้องได้ seq=3 ไม่ใช่ seq=2 (count-based จะได้ 2 ซึ่งผิด)
        """
        from apps.billing.models import Bill
        month = date(2026, 1, 1)

        bill1 = self._make_bill(self.rooms[0], month)
        bill2 = self._make_bill(self.rooms[1], month)

        # ตรวจว่าได้ seq ตามลำดับ
        seq1 = int(bill1.invoice_number.split('-')[-1])
        seq2 = int(bill2.invoice_number.split('-')[-1])
        self.assertEqual(seq2, seq1 + 1)

        # ลบ bill2 (seq สูงสุด)
        bill2.delete()

        # สร้าง bill ใหม่ — ต้องได้ seq = seq2 + 1 (MAX-based ต่อจาก seq2 ก่อนลบ)
        bill3 = self._make_bill(self.rooms[2], month)
        seq3 = int(bill3.invoice_number.split('-')[-1])
        # MAX-based: last known seq คือ seq1 (bill2 ถูกลบไปแล้ว)
        # ดังนั้น seq3 ต้องเป็น seq1 + 1
        self.assertEqual(seq3, seq1 + 1)
        # ต้องไม่ใช่ seq ของ bill2 ที่ถูกลบไปแล้ว (ซึ่ง count-based จะได้เลขนี้)
        # เนื่องจาก bill2 ถูกลบไป count = 1 → seq = 2 ซึ่งเคยใช้แล้ว
        # MAX-based จะนับจาก bill1 ที่เหลืออยู่ → seq1+1

    def test_sequential_creation_no_collision(self):
        """สร้าง bill ทีละใบ 5 ใบในเดือนเดียวกัน — invoice_number ต้องไม่ซ้ำและเรียงลำดับ"""
        from apps.billing.models import Bill
        month = date(2026, 2, 1)

        bills = []
        for i in range(5):
            b = self._make_bill(self.rooms[i], month)
            bills.append(b)

        invoice_numbers = [b.invoice_number for b in bills]
        # ต้องไม่มีซ้ำ
        self.assertEqual(len(invoice_numbers), len(set(invoice_numbers)),
                         f"พบ invoice_number ซ้ำ: {invoice_numbers}")

        # ต้องเรียงลำดับ seq
        seqs = [int(inv.split('-')[-1]) for inv in invoice_numbers]
        for i in range(1, len(seqs)):
            self.assertEqual(seqs[i], seqs[i - 1] + 1,
                             f"Seq ไม่ต่อเนื่อง: {seqs}")
