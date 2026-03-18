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
