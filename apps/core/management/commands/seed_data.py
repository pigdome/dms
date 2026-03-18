from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed development data for DMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing seed data before re-seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing seed data...')
            self._clear_data()

        self.stdout.write('Seeding data...')
        self._seed()

    def _clear_data(self):
        from apps.notifications.models import Parcel, Broadcast, DunningLog
        from apps.maintenance.models import MaintenanceTicket, TicketStatusHistory, TicketPhoto
        from apps.billing.models import Bill, Payment, BillingSettings
        from apps.tenants.models import TenantProfile, Lease, DigitalVault
        from apps.rooms.models import MeterReading, Room, Floor, Building
        from apps.core.models import Dormitory, CustomUser, ActivityLog

        # Delete in dependency order
        DunningLog.objects.all().delete()
        Parcel.objects.all().delete()
        Broadcast.objects.all().delete()
        TicketStatusHistory.objects.all().delete()
        TicketPhoto.objects.all().delete()
        MaintenanceTicket.objects.all().delete()
        Payment.objects.all().delete()
        Bill.objects.all().delete()
        MeterReading.objects.all().delete()
        Lease.objects.all().delete()
        DigitalVault.objects.all().delete()
        TenantProfile.objects.all().delete()
        ActivityLog.objects.all().delete()
        BillingSettings.objects.all().delete()
        Room.objects.all().delete()
        Floor.objects.all().delete()
        Building.objects.all().delete()
        CustomUser.objects.filter(username__in=[
            'owner1', 'staff1',
            'tenant101', 'tenant102', 'tenant201', 'tenant202', 'tenant105',
        ]).delete()
        Dormitory.objects.filter(name='หอพักสุขสบาย').delete()

        self.stdout.write('Existing seed data cleared.')

    def _seed(self):
        from apps.core.models import Dormitory, CustomUser
        from apps.billing.models import BillingSettings, Bill
        from apps.rooms.models import Building, Floor, Room, MeterReading
        from apps.tenants.models import TenantProfile, Lease
        from apps.maintenance.models import MaintenanceTicket
        from apps.notifications.models import Parcel

        today = date.today()
        # First day of current month
        current_month_first = today.replace(day=1)
        # First day of last month
        if today.month == 1:
            last_month_first = today.replace(year=today.year - 1, month=12, day=1)
        else:
            last_month_first = today.replace(month=today.month - 1, day=1)

        # ── Dormitory ──────────────────────────────────────────────────────────
        dormitory, _ = Dormitory.objects.get_or_create(
            name='หอพักสุขสบาย',
            defaults={
                'address': '123 ถนนพหลโยธิน แขวงลาดยาว เขตจตุจักร กรุงเทพฯ 10900',
            },
        )

        # ── BillingSettings ───────────────────────────────────────────────────
        BillingSettings.objects.get_or_create(
            dormitory=dormitory,
            defaults={
                'bill_day': 1,
                'grace_days': 5,
                'elec_rate': 7.00,
                'water_rate': 18.00,
                'dunning_enabled': True,
            },
        )

        # ── Buildings ─────────────────────────────────────────────────────────
        building_a, _ = Building.objects.get_or_create(
            dormitory=dormitory,
            name='อาคาร A',
        )
        building_b, _ = Building.objects.get_or_create(
            dormitory=dormitory,
            name='อาคาร B',
        )

        # ── Floors (3 per building) ───────────────────────────────────────────
        floors_a = {}
        floors_b = {}
        for floor_num in [1, 2, 3]:
            floor_a, _ = Floor.objects.get_or_create(building=building_a, number=floor_num)
            floor_b, _ = Floor.objects.get_or_create(building=building_b, number=floor_num)
            floors_a[floor_num] = floor_a
            floors_b[floor_num] = floor_b

        # ── Rooms ─────────────────────────────────────────────────────────────
        room_defs = [
            # (floor_obj, number, status)
            (floors_a[1], '101', Room.Status.OCCUPIED),
            (floors_a[1], '102', Room.Status.OCCUPIED),
            (floors_a[1], '103', Room.Status.VACANT),
            (floors_a[1], '104', Room.Status.CLEANING),
            (floors_a[2], '201', Room.Status.OCCUPIED),
            (floors_a[2], '202', Room.Status.OCCUPIED),
            (floors_a[2], '203', Room.Status.VACANT),
            (floors_b[1], '105', Room.Status.OCCUPIED),
            (floors_b[1], '106', Room.Status.MAINTENANCE),
        ]

        rooms = {}
        for floor_obj, number, status in room_defs:
            room, created = Room.objects.get_or_create(
                floor=floor_obj,
                number=number,
                defaults={'base_rent': 5000, 'status': status},
            )
            if not created:
                room.base_rent = 5000
                room.status = status
                room.save()
            rooms[number] = room

        # ── Users ─────────────────────────────────────────────────────────────
        def get_or_create_user(username, email, password, role, first_name, last_name, dorm=None):
            user, created = CustomUser.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'role': role,
                    'dormitory': dorm,
                    'first_name': first_name,
                    'last_name': last_name,
                },
            )
            if created:
                user.set_password(password)
                user.save()
            return user

        owner_user = get_or_create_user(
            username='owner1',
            email='owner1@test.com',
            password='test1234',
            role=CustomUser.Role.OWNER,
            first_name='สมชาย',
            last_name='เจ้าของ',
            dorm=dormitory,
        )

        staff_user = get_or_create_user(
            username='staff1',
            email='staff1@test.com',
            password='test1234',
            role=CustomUser.Role.STAFF,
            first_name='สมหมาย',
            last_name='พนักงาน',
            dorm=dormitory,
        )

        tenant_defs = [
            ('tenant101', 'tenant101@test.com', 'วิภา',   'สายลม', '101'),
            ('tenant102', 'tenant102@test.com', 'เดชา',   'มีสุข', '102'),
            ('tenant201', 'tenant201@test.com', 'รัตนา',  'ดีจริง', '201'),
            ('tenant202', 'tenant202@test.com', 'นพดล',   'ใจดี',  '202'),
            ('tenant105', 'tenant105@test.com', 'สุภา',   'รักดี', '105'),
        ]

        tenant_users = {}
        for username, email, first_name, last_name, room_num in tenant_defs:
            user = get_or_create_user(
                username=username,
                email=email,
                password='test1234',
                role=CustomUser.Role.TENANT,
                first_name=first_name,
                last_name=last_name,
                dorm=dormitory,
            )
            tenant_users[room_num] = user

        # ── TenantProfiles & Leases ───────────────────────────────────────────
        phone_map = {
            '101': '081-234-5678',
            '102': '082-345-6789',
            '201': '083-456-7890',
            '202': '084-567-8901',
            '105': '085-678-9012',
        }

        tenant_profiles = {}
        for room_num, user in tenant_users.items():
            profile, _ = TenantProfile.objects.get_or_create(
                user=user,
                defaults={
                    'room': rooms[room_num],
                    'phone': phone_map[room_num],
                    'line_id': user.username,
                },
            )
            tenant_profiles[room_num] = profile

            Lease.objects.get_or_create(
                tenant=profile,
                start_date=date(2025, 1, 1),
                defaults={
                    'end_date': date(2025, 12, 31),
                },
            )

        # ── MeterReadings ─────────────────────────────────────────────────────
        occupied_rooms = ['101', '102', '201', '202', '105']
        for room_num in occupied_rooms:
            MeterReading.objects.get_or_create(
                room=rooms[room_num],
                reading_date=current_month_first,
                defaults={
                    'water_prev': 1000,
                    'water_curr': 1015,
                    'elec_prev': 5000,
                    'elec_curr': 5120,
                    'recorded_by': staff_user,
                },
            )

        # ── Bills ─────────────────────────────────────────────────────────────
        due_date = current_month_first.replace(day=5)
        paid_rooms = {'101', '201'}

        for room_num in occupied_rooms:
            status = Bill.Status.PAID if room_num in paid_rooms else Bill.Status.SENT
            Bill.objects.get_or_create(
                room=rooms[room_num],
                month=current_month_first,
                defaults={
                    'base_rent': 5000,
                    'water_amt': 270,   # 15 units * 18
                    'elec_amt': 840,    # 120 units * 7
                    'total': 6110,      # 5000 + 270 + 840
                    'due_date': due_date,
                    'status': status,
                },
            )

        # ── MaintenanceTickets ────────────────────────────────────────────────
        MaintenanceTicket.objects.get_or_create(
            room=rooms['102'],
            description='แอร์ไม่เย็น',
            defaults={
                'reported_by': tenant_users['102'],
                'status': MaintenanceTicket.Status.IN_PROGRESS,
                'technician': 'ช่างแดง',
            },
        )

        MaintenanceTicket.objects.get_or_create(
            room=rooms['201'],
            description='ก๊อกน้ำรั่ว',
            defaults={
                'reported_by': tenant_users['201'],
                'status': MaintenanceTicket.Status.NEW,
            },
        )

        # ── Parcels ───────────────────────────────────────────────────────────
        Parcel.objects.get_or_create(
            room=rooms['101'],
            carrier='Kerry Express',
            defaults={
                'logged_by': staff_user,
                'photo': '',
            },
        )

        Parcel.objects.get_or_create(
            room=rooms['102'],
            carrier='Flash Express',
            defaults={
                'logged_by': staff_user,
                'photo': '',
            },
        )

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write('=== Seed Data Created ===')
        self.stdout.write(f'Dormitory: {dormitory.name}')
        self.stdout.write('Buildings: 2 (อาคาร A, อาคาร B)')
        self.stdout.write(f'Rooms: {len(rooms)}')
        self.stdout.write(f'Tenants: {len(tenant_users)}')
        self.stdout.write('')
        self.stdout.write('Login credentials:')
        self.stdout.write('  Superadmin: admin      / admin1234')
        self.stdout.write('  Owner:      owner1     / test1234')
        self.stdout.write('  Staff:      staff1     / test1234')
        self.stdout.write('  Tenant:     tenant101  / test1234')
        self.stdout.write('========================')
