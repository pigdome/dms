from django.test import SimpleTestCase

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

from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings


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
