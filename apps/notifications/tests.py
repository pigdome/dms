from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.notifications.models import DunningLog


class DunningLogTriggerTypeTests(SimpleTestCase):
    """Verify DunningLog.TriggerType choices are complete (no DB required)."""

    EXPECTED_TRIGGER_TYPES = {
        'pre_7d',
        'pre_3d',
        'pre_1d',
        'due',
        'post_1d',
        'post_7d',
        'post_15d',
    }

    def test_dunning_log_trigger_type_choices_complete(self):
        """All 7 dunning trigger type values must be present."""
        actual_values = {choice[0] for choice in DunningLog.TriggerType.choices}
        self.assertEqual(actual_values, self.EXPECTED_TRIGGER_TYPES)

    def test_dunning_log_has_exactly_seven_trigger_types(self):
        """There should be exactly 7 trigger types — no more, no less."""
        self.assertEqual(len(DunningLog.TriggerType.choices), 7)

    def test_dunning_log_trigger_type_labels(self):
        """Each trigger type must map to a non-empty human-readable label."""
        choices = dict(DunningLog.TriggerType.choices)
        self.assertTrue(choices['pre_7d'])
        self.assertTrue(choices['pre_3d'])
        self.assertTrue(choices['pre_1d'])
        self.assertTrue(choices['due'])
        self.assertTrue(choices['post_1d'])
        self.assertTrue(choices['post_7d'])
        self.assertTrue(choices['post_15d'])


# ---------------------------------------------------------------------------
# LINE module tests (no real HTTP calls)
# ---------------------------------------------------------------------------


class LINEPushTextTests(TestCase):
    """push_text() — unit tests with mocked urllib."""

    def _push(self, line_id, text, token='tok', status=200):
        mock_resp = MagicMock()
        mock_resp.status = status
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        with override_settings(LINE_CHANNEL_ACCESS_TOKEN=token):
            with patch('urllib.request.urlopen', return_value=mock_resp) as mock_open:
                from apps.notifications.line import push_text
                result = push_text(line_id, text)
                return result, mock_open

    def test_returns_true_on_200(self):
        result, _ = self._push('Uxxx', 'hello')
        self.assertTrue(result)

    def test_returns_false_on_http_error(self):
        import urllib.error
        err = urllib.error.HTTPError(url='', code=400, msg='Bad', hdrs={}, fp=MagicMock())
        err.read = lambda: b'error'
        with override_settings(LINE_CHANNEL_ACCESS_TOKEN='tok'):
            with patch('urllib.request.urlopen', side_effect=err):
                from apps.notifications import line as line_mod
                import importlib; importlib.reload(line_mod)
                result = line_mod.push_text('Uxxx', 'hello')
        self.assertFalse(result)

    def test_skips_when_no_token(self):
        with override_settings(LINE_CHANNEL_ACCESS_TOKEN=''):
            from apps.notifications.line import push_text
            result = push_text('Uxxx', 'hello')
        self.assertFalse(result)

    def test_skips_when_empty_line_id(self):
        with override_settings(LINE_CHANNEL_ACCESS_TOKEN='tok'):
            with patch('urllib.request.urlopen') as mock_open:
                from apps.notifications.line import push_text
                result = push_text('', 'hello')
        self.assertFalse(result)
        mock_open.assert_not_called()

    def test_request_sends_correct_payload(self):
        import json
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        with override_settings(LINE_CHANNEL_ACCESS_TOKEN='my-token'):
            with patch('urllib.request.urlopen', return_value=mock_resp):
                with patch('urllib.request.Request') as mock_req_cls:
                    from apps.notifications import line as line_mod
                    import importlib; importlib.reload(line_mod)
                    line_mod.push_text('U123', 'Hi there')
                    call_kwargs = mock_req_cls.call_args
                    data_arg = call_kwargs[1].get('data') or call_kwargs[0][1]
                    payload = json.loads(data_arg.decode())
                    self.assertEqual(payload['to'], 'U123')
                    self.assertEqual(payload['messages'][0]['text'], 'Hi there')
                    headers = call_kwargs[1].get('headers') or call_kwargs[0][2]
                    self.assertIn('my-token', headers.get('Authorization', ''))


# ---------------------------------------------------------------------------
# SMSService tests (no real HTTP calls)
# ---------------------------------------------------------------------------


class SMSServiceTests(SimpleTestCase):
    """SMSService.send_sms() — unit tests with mocked requests.post."""

    def _make_svc(self, api_key='test-api-key', sender='DORM'):
        from apps.notifications.sms import SMSService
        return SMSService(api_key=api_key, sender_name=sender)

    def test_returns_true_on_success(self):
        """ส่ง SMS สำเร็จ — requests.post คืน 200."""
        svc = self._make_svc()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        with patch('apps.notifications.sms.requests.post', return_value=mock_resp) as mock_post:
            result = svc.send_sms(phone='0812345678', message='test')
        self.assertTrue(result)
        mock_post.assert_called_once()

    def test_returns_false_when_no_api_key(self):
        """ถ้าไม่มี api_key ให้ graceful degrade — คืน False โดยไม่ crash."""
        from apps.notifications.sms import SMSService
        svc = SMSService(api_key='', sender_name='')
        with patch('apps.notifications.sms.requests.post') as mock_post:
            result = svc.send_sms(phone='0812345678', message='test')
        self.assertFalse(result)
        mock_post.assert_not_called()

    def test_returns_false_when_empty_phone(self):
        """ถ้าไม่มีหมายเลขโทรศัพท์ ให้คืน False."""
        svc = self._make_svc()
        with patch('apps.notifications.sms.requests.post') as mock_post:
            result = svc.send_sms(phone='', message='test')
        self.assertFalse(result)
        mock_post.assert_not_called()

    def test_returns_false_on_http_error(self):
        """ถ้า HTTP error ให้คืน False."""
        import requests as req_lib
        svc = self._make_svc()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        http_err = req_lib.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_err
        with patch('apps.notifications.sms.requests.post', return_value=mock_resp):
            result = svc.send_sms(phone='0812345678', message='test')
        self.assertFalse(result)

    def test_returns_false_on_timeout(self):
        """ถ้า timeout ให้คืน False."""
        import requests as req_lib
        svc = self._make_svc()
        with patch('apps.notifications.sms.requests.post', side_effect=req_lib.exceptions.Timeout):
            result = svc.send_sms(phone='0812345678', message='test')
        self.assertFalse(result)

    def test_phone_normalization_thai(self):
        """แปลงเบอร์ไทย 08x → +668x ก่อนส่ง."""
        from apps.notifications.sms import SMSService
        self.assertEqual(SMSService._normalize_phone('0812345678'), '+66812345678')
        self.assertEqual(SMSService._normalize_phone('+66812345678'), '+66812345678')
        self.assertEqual(SMSService._normalize_phone('66812345678'), '+66812345678')

    def test_settings_fallback_for_api_key(self):
        """ถ้าไม่ส่ง api_key ตอนสร้าง instance ให้อ่านจาก settings."""
        from apps.notifications.sms import SMSService
        with override_settings(SMS_API_KEY='from-settings', SMS_SENDER_NAME='TEST'):
            svc = SMSService()
        self.assertEqual(svc.api_key, 'from-settings')
        self.assertEqual(svc.sender_name, 'TEST')


# ---------------------------------------------------------------------------
# Dunning channel routing tests (_deliver_dunning)
# ---------------------------------------------------------------------------


class DeliverDunningChannelTests(SimpleTestCase):
    """
    ทดสอบ logic การเลือก channel ใน _deliver_dunning():
      - line_only  → เรียก push_dunning_message เท่านั้น
      - sms_only   → เรียก _send_sms_dunning เท่านั้น
      - both       → เรียกทั้งคู่
      - both + LINE fail → LINE ล้มเหลวแต่ยัง call SMS (fallback)

    ใช้ SimpleTestCase เพราะ mock BillingSettings.objects.get — ไม่ต้องการ DB.
    """

    def _make_bill(self):
        """สร้าง mock Bill object ที่มี dormitory."""
        bill = MagicMock()
        bill.invoice_number = 'INV-2601-001'
        bill.room.number = '101'
        bill.room.floor.building.dormitory = MagicMock()
        bill.due_date = None
        bill.total = 5000
        bill.month = None
        return bill

    def _make_billing_settings(self, channel: str, sms_api_key: str = 'key'):
        settings = MagicMock()
        settings.notification_channel = channel
        settings.sms_api_key = sms_api_key
        settings.sms_sender_name = 'DORM'
        return settings

    def test_line_only_calls_line_not_sms(self):
        """channel=line_only → ส่งแค่ LINE, ไม่แตะ SMS."""
        bill = self._make_bill()
        bs = self._make_billing_settings('line_only')

        with patch('apps.billing.models.BillingSettings.objects') as mock_bs_mgr, \
             patch('apps.notifications.line.push_dunning_message', return_value=True) as mock_line, \
             patch('apps.notifications.tasks._send_sms_dunning') as mock_sms:

            mock_bs_mgr.get.return_value = bs
            from apps.notifications.tasks import _deliver_dunning
            _deliver_dunning(bill, 'pre_7d')

        mock_line.assert_called_once_with(bill, 'pre_7d')
        mock_sms.assert_not_called()

    def test_sms_only_calls_sms_not_line(self):
        """channel=sms_only → ส่งแค่ SMS, ไม่แตะ LINE."""
        bill = self._make_bill()
        bs = self._make_billing_settings('sms_only')

        with patch('apps.billing.models.BillingSettings.objects') as mock_bs_mgr, \
             patch('apps.notifications.line.push_dunning_message') as mock_line, \
             patch('apps.notifications.tasks._send_sms_dunning', return_value=True) as mock_sms:

            mock_bs_mgr.get.return_value = bs
            from apps.notifications.tasks import _deliver_dunning
            _deliver_dunning(bill, 'due')

        mock_sms.assert_called_once()
        mock_line.assert_not_called()

    def test_both_calls_line_and_sms(self):
        """channel=both → ส่งทั้ง LINE และ SMS."""
        bill = self._make_bill()
        bs = self._make_billing_settings('both')

        with patch('apps.billing.models.BillingSettings.objects') as mock_bs_mgr, \
             patch('apps.notifications.line.push_dunning_message', return_value=True) as mock_line, \
             patch('apps.notifications.tasks._send_sms_dunning', return_value=True) as mock_sms:

            mock_bs_mgr.get.return_value = bs
            from apps.notifications.tasks import _deliver_dunning
            _deliver_dunning(bill, 'post_1d')

        mock_line.assert_called_once_with(bill, 'post_1d')
        mock_sms.assert_called_once()

    def test_both_line_fail_still_sends_sms(self):
        """channel=both และ LINE ล้มเหลว → ยังส่ง SMS (fallback)."""
        bill = self._make_bill()
        bs = self._make_billing_settings('both')

        with patch('apps.billing.models.BillingSettings.objects') as mock_bs_mgr, \
             patch('apps.notifications.line.push_dunning_message', return_value=False) as mock_line, \
             patch('apps.notifications.tasks._send_sms_dunning', return_value=True) as mock_sms:

            mock_bs_mgr.get.return_value = bs
            from apps.notifications.tasks import _deliver_dunning
            _deliver_dunning(bill, 'post_7d')

        # LINE ถูก call แต่คืน False
        mock_line.assert_called_once_with(bill, 'post_7d')
        # SMS ยังต้องถูก call แม้ LINE จะล้มเหลว
        mock_sms.assert_called_once()

    def test_no_billing_settings_falls_back_to_line(self):
        """ถ้าไม่มี BillingSettings → fallback เป็น LINE (เหมือนพฤติกรรมเดิม)."""
        bill = self._make_bill()

        with patch('apps.billing.models.BillingSettings.objects') as mock_bs_mgr, \
             patch('apps.notifications.line.push_dunning_message', return_value=True) as mock_line, \
             patch('apps.notifications.tasks._send_sms_dunning') as mock_sms:

            from apps.billing.models import BillingSettings
            mock_bs_mgr.get.side_effect = BillingSettings.DoesNotExist
            from apps.notifications.tasks import _deliver_dunning
            _deliver_dunning(bill, 'pre_3d')

        mock_line.assert_called_once_with(bill, 'pre_3d')
        mock_sms.assert_not_called()


# ---------------------------------------------------------------------------
# Payment notification tests (receipt to tenant + alert to owner)
# ---------------------------------------------------------------------------


class PushPaymentReceiptTests(SimpleTestCase):
    """push_payment_receipt() — sends digital receipt to tenant(s) via LINE."""

    def _make_bill_and_payment(self):
        from datetime import date, datetime
        bill = MagicMock()
        bill.room.number = '201'
        bill.invoice_number = 'INV-2601-005'
        bill.month = date(2026, 1, 1)

        payment = MagicMock()
        payment.amount = 5500.00
        payment.paid_at = datetime(2026, 1, 15, 14, 30)

        return bill, payment

    def test_sends_receipt_to_tenant_with_line_id(self):
        """Tenant with line_id receives a receipt message."""
        bill, payment = self._make_bill_and_payment()
        profile = MagicMock()
        profile.line_id = 'Utenant123'
        bill.room.tenant_profiles.filter.return_value.select_related.return_value = [profile]

        with patch('apps.notifications.line.push_text', return_value=True) as mock_push:
            from apps.notifications.line import push_payment_receipt
            result = push_payment_receipt(bill, payment)

        self.assertTrue(result)
        mock_push.assert_called_once()
        call_args = mock_push.call_args
        self.assertEqual(call_args[0][0], 'Utenant123')
        self.assertIn('INV-2601-005', call_args[0][1])
        self.assertIn('5,500.00', call_args[0][1])

    def test_skips_tenant_without_line_id(self):
        """Tenant without line_id is skipped gracefully."""
        bill, payment = self._make_bill_and_payment()
        profile = MagicMock()
        profile.line_id = ''
        bill.room.tenant_profiles.filter.return_value.select_related.return_value = [profile]

        with patch('apps.notifications.line.push_text') as mock_push:
            from apps.notifications.line import push_payment_receipt
            result = push_payment_receipt(bill, payment)

        self.assertFalse(result)
        mock_push.assert_not_called()

    def test_returns_false_on_exception(self):
        """Returns False when tenant_profiles query raises exception."""
        bill, payment = self._make_bill_and_payment()
        bill.room.tenant_profiles.filter.side_effect = Exception('DB error')

        from apps.notifications.line import push_payment_receipt
        result = push_payment_receipt(bill, payment)

        self.assertFalse(result)


class PushPaymentOwnerNotificationTests(SimpleTestCase):
    """push_payment_owner_notification() — notifies owner(s) via LINE."""

    def _make_bill_and_payment(self):
        from datetime import date, datetime
        bill = MagicMock()
        bill.room.number = '301'
        bill.room.floor.building.dormitory = MagicMock()
        bill.invoice_number = 'INV-2601-010'
        bill.month = date(2026, 1, 1)

        payment = MagicMock()
        payment.amount = 8000.00
        payment.paid_at = datetime(2026, 1, 20, 10, 0)

        return bill, payment

    def test_notifies_owner_with_line_user_id(self):
        """Owner with line_user_id receives payment notification."""
        bill, payment = self._make_bill_and_payment()
        owner = MagicMock()
        owner.line_user_id = 'Uowner456'

        mock_qs = MagicMock()
        mock_qs.exists.return_value = True
        mock_qs.__iter__ = lambda s: iter([owner])

        with patch('apps.core.models.CustomUser.objects') as mock_mgr, \
             patch('apps.notifications.line.push_text', return_value=True) as mock_push:
            mock_mgr.filter.return_value.exclude.return_value = mock_qs
            from apps.notifications.line import push_payment_owner_notification
            result = push_payment_owner_notification(bill, payment)

        self.assertTrue(result)
        mock_push.assert_called_once()
        call_args = mock_push.call_args
        self.assertEqual(call_args[0][0], 'Uowner456')
        self.assertIn('INV-2601-010', call_args[0][1])
        self.assertIn('8,000.00', call_args[0][1])

    def test_no_owner_with_line_id_returns_false(self):
        """Returns False when no owner has a line_user_id configured."""
        bill, payment = self._make_bill_and_payment()

        empty_qs = MagicMock()
        empty_qs.exists.return_value = False
        empty_qs.__iter__ = lambda s: iter([])

        with patch('apps.core.models.CustomUser.objects') as mock_mgr, \
             patch('apps.core.models.UserDormitoryRole.objects') as mock_udr, \
             patch('apps.notifications.line.push_text') as mock_push:
            mock_mgr.filter.return_value.exclude.return_value = empty_qs
            mock_udr.filter.return_value.values_list.return_value = []

            from apps.notifications.line import push_payment_owner_notification
            result = push_payment_owner_notification(bill, payment)

        self.assertFalse(result)
        mock_push.assert_not_called()


class TMRWebhookNotificationTests(TestCase):
    """
    Verify that the TMR webhook dispatches payment notification tasks
    after successfully processing a payment.
    """

    def _create_test_bill(self):
        """Create a minimal bill with all required FK chain for webhook test."""
        from apps.core.models import Dormitory
        from apps.rooms.models import Building, Floor, Room
        from apps.billing.models import Bill, BillingSettings
        from datetime import date, timedelta

        dorm = Dormitory.objects.create(name='Test Dorm', address='123 Test St')
        BillingSettings.objects.create(dormitory=dorm)
        building = Building.objects.create(dormitory=dorm, name='A')
        floor = Floor.objects.create(building=building, number=1)
        room = Room.objects.create(floor=floor, number='101', base_rent=5000, status='occupied')
        bill = Bill.unscoped_objects.create(
            dormitory=dorm,
            room=room,
            month=date(2026, 1, 1),
            base_rent=5000,
            total=5500,
            due_date=date(2026, 1, 31),
            status='sent',
            invoice_number='TEST-2601-001',
        )
        return bill

    @override_settings(TMR_WEBHOOK_SECRET='')
    def test_webhook_dispatches_receipt_and_owner_tasks(self):
        """After successful payment, webhook queues both notification tasks."""
        import json
        bill = self._create_test_bill()

        payload = json.dumps({
            'ref': 'txn-unique-001',
            'order_id': bill.invoice_number,
            'amount': '5500.00',
            'tmr_ref': 'TMR-REF-001',
        })

        with patch('apps.notifications.tasks.send_payment_receipt_task.delay') as mock_receipt, \
             patch('apps.notifications.tasks.send_payment_owner_notification_task.delay') as mock_owner:
            response = self.client.post(
                '/billing/webhook/tmr/',
                data=payload,
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        bill.refresh_from_db()
        self.assertEqual(bill.status, 'paid')
        mock_receipt.assert_called_once_with(bill.pk)
        mock_owner.assert_called_once_with(bill.pk)
