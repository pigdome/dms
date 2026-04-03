import json
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class UUIDEncoder(json.JSONEncoder):
    """JSON encoder that converts UUID objects to strings."""
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


class TenantManager(models.Manager):
    """Automatic filtering by the current thread-local dormitory."""
    def get_queryset(self):
        from apps.core.threadlocal import get_current_dormitory
        dorm = get_current_dormitory()
        qs = super().get_queryset()
        if dorm:
            # Handle both model instances and PKs
            dorm_id = dorm.pk if hasattr(dorm, 'pk') else dorm
            return qs.filter(dormitory_id=dorm_id)
        return qs


class TenantModelMixin(models.Model):
    """Abstract base for models that belong to a dormitory (tenant)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dormitory = models.ForeignKey('core.Dormitory', on_delete=models.CASCADE, null=True, blank=True)

    objects = TenantManager()
    unscoped_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Safely check for dormitory_id to avoid "deferred field" errors on unsaved models
        dorm_id = getattr(self, 'dormitory_id', None)
        if not dorm_id:
            from apps.core.threadlocal import get_current_dormitory
            dorm = get_current_dormitory()
            if dorm:
                self.dormitory_id = dorm.pk if hasattr(dorm, 'pk') else dorm
        super().save(*args, **kwargs)


class Dormitory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    address = models.TextField()
    photo = models.ImageField(upload_to='dormitory/', blank=True, null=True)
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    location_lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    invoice_prefix = models.CharField(
        max_length=5, blank=True,
        help_text='Prefix for invoice numbers, e.g. H01'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Dormitories'

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Role(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Superadmin'
        OWNER = 'owner', 'Owner'
        # Building Manager: สิทธิ์ระหว่าง owner กับ staff — ดูแลเฉพาะตึกที่ assign ให้
        BUILDING_MANAGER = 'building_manager', 'Building Manager'
        STAFF = 'staff', 'Staff'
        TENANT = 'tenant', 'Tenant'

    class Theme(models.TextChoices):
        LIGHT = 'light', 'Light'
        DARK = 'dark', 'Dark'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TENANT)
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.LIGHT)
    line_user_id = models.CharField(
        max_length=100, blank=True,
        help_text='LINE User ID for push notifications (owner/staff)',
    )
    dormitory = models.ForeignKey(
        Dormitory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='users',
        help_text='Active/current dormitory context for this user'
    )
    # I5: บังคับ user เปลี่ยน password เมื่อ login ครั้งแรก
    # set เป็น True เมื่อสร้าง account โดย owner/staff
    must_change_password = models.BooleanField(
        default=False,
        help_text='Force user to change password on next login',
    )
    dormitories = models.ManyToManyField(
        Dormitory,
        through='UserDormitoryRole',
        related_name='members',
        blank=True,
    )
    # Buildings ที่ building_manager ดูแล — ใช้เฉพาะ role=building_manager
    managed_buildings = models.ManyToManyField(
        'rooms.Building',
        blank=True,
        related_name='managers',
        help_text='Buildings assigned to this user (building_manager role only)',
    )

    def __str__(self):
        return f'{self.username} ({self.role})'

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_building_manager(self):
        return self.role == self.Role.BUILDING_MANAGER

    @property
    def is_staff_member(self):
        return self.role == self.Role.STAFF

    @property
    def is_tenant_user(self):
        return self.role == self.Role.TENANT

    @property
    def owned_dormitories(self):
        return Dormitory.objects.filter(
            userdormitoryrole__user=self,
            userdormitoryrole__role=self.Role.OWNER,
        )


class UserDormitoryRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='dormitory_memberships')
    dormitory = models.ForeignKey(Dormitory, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=CustomUser.Role.choices, default=CustomUser.Role.STAFF)
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = [('user', 'dormitory')]

    def __str__(self):
        return f'{self.user} @ {self.dormitory} ({self.role})'


class StaffPermission(models.Model):
    """
    I2: Granular permission matrix สำหรับ staff user
    Owner สร้าง/แก้ไข permissions เหล่านี้ผ่าน UI (checkbox matrix)
    Staff ที่ไม่มี record นี้ถือว่าไม่มีสิทธิ์ใด ๆ เลย
    Owner/building_manager/superadmin ผ่าน check ทั้งหมดเสมอ
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='staff_permission',
        help_text='Staff user ที่ permission นี้เป็นของ',
    )
    dormitory = models.ForeignKey(
        Dormitory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='staff_permissions',
    )
    can_view_billing = models.BooleanField(default=False, help_text='ดูบิลและการชำระเงิน')
    can_record_meter = models.BooleanField(default=False, help_text='บันทึกมิเตอร์น้ำ/ไฟ')
    can_manage_maintenance = models.BooleanField(default=False, help_text='จัดการงานแจ้งซ่อม')
    can_log_parcels = models.BooleanField(default=False, help_text='บันทึกพัสดุ')
    can_view_tenants = models.BooleanField(default=False, help_text='ดูข้อมูลผู้เช่า')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Staff Permission'
        verbose_name_plural = 'Staff Permissions'

    def __str__(self):
        return f'StaffPermission({self.user.username})'


class ActivityLog(TenantModelMixin):
    # Action types used by AuditMixin
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'

    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=200)
    detail = models.JSONField(default=dict, blank=True, encoder=UUIDEncoder)
    # Fields for structured audit trail (เพิ่มเพื่อ track old/new value ของ critical models)
    model_name = models.CharField(max_length=100, blank=True)
    record_id = models.CharField(max_length=100, blank=True, null=True,
                                  help_text='PK of the affected record (UUID or int as string)')
    old_value = models.JSONField(null=True, blank=True, encoder=UUIDEncoder,
                                  help_text='Snapshot of changed fields before save')
    new_value = models.JSONField(null=True, blank=True, encoder=UUIDEncoder,
                                  help_text='Snapshot of changed fields after save')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.action} at {self.created_at}'
