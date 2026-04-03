import calendar
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


def _months_ago(n, today=None):
    """Return the first day of the month n months before today."""
    if today is None:
        today = date.today()
    m = today.month - n
    y = today.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _due_date(month_first, bill_day=1, grace_days=5):
    last_day = calendar.monthrange(month_first.year, month_first.month)[1]
    d = min(bill_day, last_day)
    return month_first.replace(day=d) + timedelta(days=grace_days)


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
        from apps.core.models import Dormitory, CustomUser, ActivityLog, UserDormitoryRole

        seed_usernames = [
            'owner1', 'staff1',
            'tenant101', 'tenant102', 'tenant201', 'tenant202', 'tenant105',
        ]

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
        UserDormitoryRole.objects.filter(user__username__in=seed_usernames).delete()
        CustomUser.objects.filter(username__in=seed_usernames).delete()
        Dormitory.objects.filter(name='หอพักสุขสบาย').delete()

        self.stdout.write('Existing seed data cleared.')

    def _seed(self):
        from apps.core.models import Dormitory, CustomUser, UserDormitoryRole
        from apps.billing.models import BillingSettings, Bill, Payment
        from apps.rooms.models import Building, Floor, Room, MeterReading
        from apps.tenants.models import TenantProfile, Lease
        from apps.maintenance.models import MaintenanceTicket, TicketStatusHistory
        from apps.notifications.models import Parcel, Broadcast, DunningLog

        today = date.today()

        def mo(n):
            """First day of the month n months ago."""
            return _months_ago(n, today)

        # ── Dormitory ──────────────────────────────────────────────────────────
        dormitory, _ = Dormitory.objects.get_or_create(
            name='หอพักสุขสบาย',
            defaults={
                'address': '123 ถนนพหลโยธิน แขวงลาดยาว เขตจตุจักร กรุงเทพฯ 10900',
                'invoice_prefix': 'SKS',
            },
        )

        # ── BillingSettings ───────────────────────────────────────────────────
        settings, _ = BillingSettings.objects.get_or_create(
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
        building_a, _ = Building.objects.get_or_create(dormitory=dormitory, name='อาคาร A')
        building_b, _ = Building.objects.get_or_create(dormitory=dormitory, name='อาคาร B')

        # ── Floors (3 per building) ───────────────────────────────────────────
        floors_a = {}
        floors_b = {}
        for floor_num in [1, 2, 3]:
            floors_a[floor_num], _ = Floor.objects.get_or_create(building=building_a, number=floor_num)
            floors_b[floor_num], _ = Floor.objects.get_or_create(building=building_b, number=floor_num)

        # ── Rooms ─────────────────────────────────────────────────────────────
        room_defs = [
            # (floor, number, status, rent)
            (floors_a[1], '101', Room.Status.OCCUPIED,    5000),
            (floors_a[1], '102', Room.Status.OCCUPIED,    5000),
            (floors_a[1], '103', Room.Status.VACANT,      5000),
            (floors_a[1], '104', Room.Status.CLEANING,    5000),
            (floors_a[2], '201', Room.Status.OCCUPIED,    6000),
            (floors_a[2], '202', Room.Status.OCCUPIED,    6000),
            (floors_a[2], '203', Room.Status.VACANT,      6000),
            (floors_b[1], '105', Room.Status.OCCUPIED,    4500),
            (floors_b[1], '106', Room.Status.MAINTENANCE, 4500),
        ]

        rooms = {}
        for floor_obj, number, status, rent in room_defs:
            room, created = Room.objects.get_or_create(
                floor=floor_obj,
                number=number,
                defaults={'base_rent': rent, 'status': status},
            )
            if not created:
                room.base_rent = rent
                room.status = status
                room.save()
            rooms[number] = room

        # ── Users ─────────────────────────────────────────────────────────────
        def _user(username, email, password, role, first_name, last_name, dorm=None):
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

        owner_user = _user('owner1', 'owner1@test.com', 'test1234',
                           CustomUser.Role.OWNER, 'สมชาย', 'เจ้าของ', dorm=dormitory)
        staff_user  = _user('staff1', 'staff1@test.com', 'test1234',
                            CustomUser.Role.STAFF, 'สมหมาย', 'พนักงาน', dorm=dormitory)

        # StaffPermission: ให้ staff1 เข้าถึงทุก feature (สำหรับ dev/demo)
        from apps.core.models import StaffPermission
        StaffPermission.objects.get_or_create(
            user=staff_user, dormitory=dormitory,
            defaults={
                'can_view_billing': True,
                'can_record_meter': True,
                'can_manage_maintenance': True,
                'can_log_parcels': True,
                'can_view_tenants': True,
            },
        )

        # Register owner in UserDormitoryRole (required for property_switch)
        UserDormitoryRole.objects.get_or_create(
            user=owner_user, dormitory=dormitory,
            defaults={'role': 'owner', 'is_primary': True},
        )

        # Tenants: (username, email, first, last, room, phone)
        tenant_defs = [
            ('tenant101', 'tenant101@test.com', 'วิภา',  'สายลม',  '101', '081-234-5678'),
            ('tenant102', 'tenant102@test.com', 'เดชา',  'มีสุข',  '102', '082-345-6789'),
            ('tenant201', 'tenant201@test.com', 'รัตนา', 'ดีจริง', '201', '083-456-7890'),
            ('tenant202', 'tenant202@test.com', 'นพดล',  'ใจดี',   '202', '084-567-8901'),
            ('tenant105', 'tenant105@test.com', 'สุภา',  'รักดี',  '105', '085-678-9012'),
        ]

        tenant_users = {}
        for username, email, first_name, last_name, room_num, _ in tenant_defs:
            tenant_users[room_num] = _user(
                username, email, 'test1234',
                CustomUser.Role.TENANT, first_name, last_name, dorm=dormitory,
            )

        # ── TenantProfiles & Leases ───────────────────────────────────────────
        phone_map = {td[4]: td[5] for td in tenant_defs}

        tenant_profiles = {}
        for _, _, _, _, room_num, phone in tenant_defs:
            user = tenant_users[room_num]
            profile, _ = TenantProfile.objects.get_or_create(
                user=user,
                defaults={
                    'room': rooms[room_num],
                    'phone': phone,
                    'line_id': user.username,
                },
            )
            tenant_profiles[room_num] = profile

            # Active lease — no end date (currently renting)
            Lease.objects.get_or_create(
                tenant=profile,
                room=rooms[room_num],
                status=Lease.Status.ACTIVE,
                defaults={'start_date': date(2025, 1, 1)},
            )

        # tenant202: ended lease from a previous room (historical context)
        Lease.objects.get_or_create(
            tenant=tenant_profiles['202'],
            room=rooms['203'],
            status=Lease.Status.ENDED,
            defaults={
                'start_date': date(2024, 6, 1),
                'end_date':   date(2024, 12, 31),
            },
        )

        # ── MeterReadings (7 months: 6 months ago → current month) ───────────
        occupied_rooms = ['101', '102', '201', '202', '105']

        # Realistic cumulative starting values
        base_water = {'101': 2000, '102': 1800, '201': 2200, '202': 1950, '105': 1600}
        base_elec  = {'101': 8000, '102': 7500, '201': 9000, '202': 8200, '105': 6800}
        # Monthly usage per room (units)
        monthly_water = {'101': 15, '102': 12, '201': 18, '202': 14, '105': 10}
        monthly_elec  = {'101': 120, '102': 100, '201': 150, '202': 130, '105': 90}

        for month_idx in range(6, -1, -1):   # 6 = oldest, 0 = current
            reading_month = mo(month_idx)
            for room_num in occupied_rooms:
                offset = 6 - month_idx          # cumulative months elapsed since base
                water_prev = base_water[room_num] + monthly_water[room_num] * offset
                water_curr = water_prev + monthly_water[room_num]
                elec_prev  = base_elec[room_num]  + monthly_elec[room_num]  * offset
                elec_curr  = elec_prev  + monthly_elec[room_num]
                MeterReading.objects.get_or_create(
                    room=rooms[room_num],
                    reading_date=reading_month,
                    defaults={
                        'water_prev': water_prev,
                        'water_curr': water_curr,
                        'elec_prev':  elec_prev,
                        'elec_curr':  elec_curr,
                        'recorded_by': staff_user,
                    },
                )

        # ── Bills (7 months) ──────────────────────────────────────────────────
        # Utility amounts per room
        water_amt = {r: monthly_water[r] * 18 for r in occupied_rooms}
        elec_amt  = {r: monthly_elec[r]  * 7  for r in occupied_rooms}

        # Bill status strategy:
        #   6–2 months ago   → PAID (all)
        #   1 month ago      → PAID (most), OVERDUE for room '102' (late payer)
        #   current month    → PAID for room '101' (paid early), SENT for the rest
        for month_idx in range(6, -1, -1):
            bill_month = mo(month_idx)
            due = _due_date(bill_month, bill_day=1, grace_days=5)

            for room_num in occupied_rooms:
                rent  = rooms[room_num].base_rent
                w_amt = water_amt[room_num]
                e_amt = elec_amt[room_num]
                total = rent + w_amt + e_amt

                if month_idx >= 2:
                    status = Bill.Status.PAID
                elif month_idx == 1:
                    status = Bill.Status.OVERDUE if room_num == '102' else Bill.Status.PAID
                else:                                   # current month
                    status = Bill.Status.PAID if room_num == '101' else Bill.Status.SENT

                meter = MeterReading.objects.filter(
                    room=rooms[room_num],
                    reading_date__year=bill_month.year,
                    reading_date__month=bill_month.month,
                ).first()

                bill, created = Bill.objects.get_or_create(
                    room=rooms[room_num],
                    month=bill_month,
                    defaults={
                        'base_rent':     rent,
                        'water_amt':     w_amt,
                        'elec_amt':      e_amt,
                        'total':         total,
                        'due_date':      due,
                        'status':        status,
                        'meter_reading': meter,
                    },
                )

                # Payment record for every PAID bill
                if status == Bill.Status.PAID and created:
                    Payment.objects.get_or_create(
                        bill=bill,
                        defaults={
                            'amount':          total,
                            'tmr_ref':         f'TXN-{bill_month.strftime("%Y%m")}-{room_num}',
                            'idempotency_key': f'TXN-{bill_month.strftime("%Y%m")}-{room_num}',
                            'webhook_payload': {},
                            'paid_at':         timezone.now(),
                        },
                    )

        # ── DunningLogs for the overdue bill (room 102, last month) ───────────
        overdue_bill = Bill.objects.filter(
            room=rooms['102'],
            month=mo(1),
            status=Bill.Status.OVERDUE,
        ).first()
        if overdue_bill:
            for trigger in ('due', 'post_1d', 'post_7d'):
                DunningLog.objects.get_or_create(
                    bill=overdue_bill,
                    trigger_type=trigger,
                    defaults={'success': True},
                )

        # ── MaintenanceTickets with full status history ────────────────────────

        # Ticket 1: Completed — light bulb in room 101
        t1, t1_new = MaintenanceTicket.objects.get_or_create(
            room=rooms['101'],
            description='หลอดไฟในห้องน้ำเสีย',
            defaults={
                'reported_by': tenant_users['101'],
                'status': MaintenanceTicket.Status.COMPLETED,
                'technician': 'ช่างสมชาย',
            },
        )
        if t1_new:
            TicketStatusHistory.objects.create(
                ticket=t1, status='new',
                changed_by=tenant_users['101'], note='แจ้งซ่อมหลอดไฟ'
            )
            TicketStatusHistory.objects.create(
                ticket=t1, status='in_progress',
                changed_by=staff_user, note='ช่างเข้าตรวจสอบแล้ว'
            )
            TicketStatusHistory.objects.create(
                ticket=t1, status='completed',
                changed_by=staff_user, note='เปลี่ยนหลอดไฟเรียบร้อย'
            )

        # Ticket 2: In Progress — AC not cold in room 102
        t2, t2_new = MaintenanceTicket.objects.get_or_create(
            room=rooms['102'],
            description='แอร์ไม่เย็น',
            defaults={
                'reported_by': tenant_users['102'],
                'status': MaintenanceTicket.Status.IN_PROGRESS,
                'technician': 'ช่างแดง',
            },
        )
        if t2_new:
            TicketStatusHistory.objects.create(
                ticket=t2, status='new',
                changed_by=tenant_users['102'], note='แจ้งซ่อมแอร์ไม่เย็น'
            )
            TicketStatusHistory.objects.create(
                ticket=t2, status='in_progress',
                changed_by=staff_user, note='ช่างรับงานและกำลังดำเนินการ'
            )

        # Ticket 3: Waiting parts — bathroom door hinge in room 202
        t3, t3_new = MaintenanceTicket.objects.get_or_create(
            room=rooms['202'],
            description='ประตูห้องน้ำบานพับหัก',
            defaults={
                'reported_by': tenant_users['202'],
                'status': MaintenanceTicket.Status.WAITING_PARTS,
                'technician': 'ช่างสมศักดิ์',
            },
        )
        if t3_new:
            TicketStatusHistory.objects.create(
                ticket=t3, status='new',
                changed_by=tenant_users['202'], note='แจ้งซ่อมประตูห้องน้ำ'
            )
            TicketStatusHistory.objects.create(
                ticket=t3, status='in_progress',
                changed_by=staff_user, note='ตรวจสอบแล้ว ต้องสั่งอะไหล่'
            )
            TicketStatusHistory.objects.create(
                ticket=t3, status='waiting_parts',
                changed_by=staff_user, note='รอสั่งบานพับอลูมิเนียม'
            )

        # Ticket 4: New — leaking tap in room 201
        t4, t4_new = MaintenanceTicket.objects.get_or_create(
            room=rooms['201'],
            description='ก๊อกน้ำรั่ว',
            defaults={
                'reported_by': tenant_users['201'],
                'status': MaintenanceTicket.Status.NEW,
            },
        )
        if t4_new:
            TicketStatusHistory.objects.create(
                ticket=t4, status='new',
                changed_by=tenant_users['201'], note='ก๊อกน้ำในห้องน้ำรั่วตลอดเวลา'
            )

        # ── Parcels ───────────────────────────────────────────────────────────
        Parcel.objects.get_or_create(
            room=rooms['101'], carrier='Kerry Express',
            defaults={'logged_by': staff_user, 'notes': 'กล่องขนาดกลาง'},
        )
        Parcel.objects.get_or_create(
            room=rooms['102'], carrier='Flash Express',
            defaults={'logged_by': staff_user, 'notes': ''},
        )
        Parcel.objects.get_or_create(
            room=rooms['201'], carrier='J&T Express',
            defaults={'logged_by': staff_user, 'notes': 'ซองเอกสาร'},
        )

        # ── Broadcasts ────────────────────────────────────────────────────────
        Broadcast.objects.get_or_create(
            dormitory=dormitory,
            title='ประกาศปิดน้ำชั่วคราว',
            defaults={
                'audience_type': 'all',
                'body': (
                    'ทางหอพักจะปิดน้ำชั่วคราวในวันเสาร์ที่ 22 มีนาคม 2568 เวลา 09:00–12:00 น. '
                    'เพื่อซ่อมแซมระบบท่อ ขออภัยในความไม่สะดวก'
                ),
                'sent_by': owner_user,
                'sent_at': timezone.now(),
            },
        )
        Broadcast.objects.get_or_create(
            dormitory=dormitory,
            title='แจ้งเตือนชำระค่าเช่าประจำเดือน',
            defaults={
                'audience_type': 'all',
                'body': 'ขอแจ้งเตือนให้ผู้เช่าทุกท่านชำระค่าเช่าประจำเดือนภายในวันที่ 5 ของทุกเดือน',
                'sent_by': owner_user,
                'sent_at': timezone.now(),
            },
        )

        # ── Summary ───────────────────────────────────────────────────────────
        bill_count = Bill.objects.filter(room__floor__building__dormitory=dormitory).count()
        self.stdout.write('')
        self.stdout.write('=== Seed Data Created ===')
        self.stdout.write(f'Dormitory:  {dormitory.name}')
        self.stdout.write('Buildings:  2 (อาคาร A, อาคาร B)')
        self.stdout.write(f'Rooms:      {len(rooms)}')
        self.stdout.write(f'Tenants:    {len(tenant_users)}')
        self.stdout.write(f'Bills:      {bill_count} (7 months × 5 rooms, with payment history)')
        self.stdout.write('Tickets:    4 (new / in_progress / waiting_parts / completed)')
        self.stdout.write('Broadcasts: 2')
        self.stdout.write('')
        self.stdout.write('Login credentials:')
        self.stdout.write('  Superadmin: admin      / admin1234')
        self.stdout.write('  Owner:      owner1     / test1234')
        self.stdout.write('  Staff:      staff1     / test1234')
        self.stdout.write('  Tenant:     tenant101  / test1234')
        self.stdout.write('========================')
