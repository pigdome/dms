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


# ---------------------------------------------------------------------------
# Pure calculation tests (no DB)
# ---------------------------------------------------------------------------

class CalculateBillTests(SimpleTestCase):
    def test_calculate_bill_basic(self):
        result = calculate_bill(base_rent=5000, water_units=10, elec_units=20, water_rate=18, elec_rate=7)
        self.assertEqual(result['base_rent'], Decimal('5000'))
        self.assertEqual(result['water_amt'], Decimal('180'))
        self.assertEqual(result['elec_amt'], Decimal('140'))
        self.assertEqual(result['total'], Decimal('5320'))

    def test_calculate_bill_zero_utilities(self):
        result = calculate_bill(base_rent=3000, water_units=0, elec_units=0, water_rate=18, elec_rate=7)
        self.assertEqual(result['water_amt'], Decimal('0'))
        self.assertEqual(result['elec_amt'], Decimal('0'))
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
        building = Building.objects.create(dormitory=cls.dorm, name='Building 1')
        floor = Floor.objects.create(building=building, number=1)
        cls.room1 = Room.objects.create(floor=floor, number='101', base_rent=5000)
        cls.room2 = Room.objects.create(floor=floor, number='102', base_rent=5000)

        cls.dorm2 = Dormitory.objects.create(
            name='Other Dorm', address='Other Addr', invoice_prefix='X99'
        )
        building2 = Building.objects.create(dormitory=cls.dorm2, name='Building X')
        floor2 = Floor.objects.create(building=building2, number=1)
        cls.room_dorm2 = Room.objects.create(floor=floor2, number='101', base_rent=4000)

    def _make_bill(self, room, month, **kwargs):
        from apps.billing.models import Bill
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
        MeterReading.objects.create(
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
        from apps.billing.models import Bill, Payment
        with self.settings(TMR_WEBHOOK_SECRET=''):
            resp = self._post({
                'ref': 'TXN-001',
                'order_id': 'WH1-2503-001',
                'amount': '5000.00',
            })
        self.assertEqual(resp.status_code, 200)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, Bill.Status.PAID)
        self.assertTrue(Payment.objects.filter(idempotency_key='TXN-001').exists())

    def test_idempotent_duplicate_returns_200(self):
        from apps.billing.models import Payment
        from django.utils import timezone
        Payment.objects.create(
            bill=self.bill,
            amount=5000,
            tmr_ref='TXN-DUP',
            idempotency_key='TXN-DUP',
            paid_at=timezone.now(),
        )
        with self.settings(TMR_WEBHOOK_SECRET=''):
            resp = self._post({
                'ref': 'TXN-DUP',
                'order_id': 'WH1-2503-001',
                'amount': '5000.00',
            })
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
        with self.settings(TMR_WEBHOOK_SECRET=''):
            resp = self._post({'order_id': 'WH1-2503-001', 'amount': '5000'})
        self.assertEqual(resp.status_code, 400)

    def test_missing_order_id_returns_400(self):
        with self.settings(TMR_WEBHOOK_SECRET=''):
            resp = self._post({'ref': 'TXN-NOID', 'amount': '5000'})
        self.assertEqual(resp.status_code, 400)

    def test_bill_not_found_returns_404(self):
        with self.settings(TMR_WEBHOOK_SECRET=''):
            resp = self._post({
                'ref': 'TXN-NOTFOUND',
                'order_id': 'NONEXISTENT-999',
                'amount': '5000',
            })
        self.assertEqual(resp.status_code, 404)

    def test_bad_json_returns_400(self):
        resp = self.client.post(
            reverse('billing:tmr_webhook'),
            data=b'not-json',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
