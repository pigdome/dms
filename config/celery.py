import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
app = Celery('dms')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Default periodic schedule — overridable via Django Celery Beat admin UI
app.conf.beat_schedule = {
    # Run at 00:05 every day; generates bills for dormitories whose bill_day == today
    'generate-monthly-bills': {
        'task': 'apps.billing.tasks.generate_monthly_bills_task',
        'schedule': crontab(hour=0, minute=5),
    },
    # Run at 00:10 every day; marks sent/draft bills past due_date as overdue
    'mark-overdue-bills': {
        'task': 'apps.billing.tasks.mark_overdue_bills_task',
        'schedule': crontab(hour=0, minute=10),
    },
    # Run at 09:00 every day; queues dunning notifications
    'check-dunning': {
        'task': 'apps.billing.tasks.check_dunning_task',
        'schedule': crontab(hour=9, minute=0),
    },
    # P1-1: Run at 08:00 every day; checks for leases expiring in 30/7 days
    'check-lease-expiry': {
        'task': 'apps.notifications.tasks.check_lease_expiry_task',
        'schedule': crontab(hour=8, minute=0),
    },
    # P1-2: Run at 02:00 every day; PDPA auto-purge 90 days after lease end
    'pdpa-auto-purge': {
        'task': 'apps.notifications.tasks.pdpa_auto_purge_task',
        'schedule': crontab(hour=2, minute=0),
    },
}
