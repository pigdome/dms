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
        STAFF = 'staff', 'Staff'
        TENANT = 'tenant', 'Tenant'

    class Theme(models.TextChoices):
        LIGHT = 'light', 'Light'
        DARK = 'dark', 'Dark'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TENANT)
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.LIGHT)
    dormitory = models.ForeignKey(
        Dormitory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='users',
        help_text='Active/current dormitory context for this user'
    )
    dormitories = models.ManyToManyField(
        Dormitory,
        through='UserDormitoryRole',
        related_name='members',
        blank=True,
    )

    def __str__(self):
        return f'{self.username} ({self.role})'

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

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


class ActivityLog(TenantModelMixin):
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=200)
    detail = models.JSONField(default=dict, blank=True, encoder=UUIDEncoder)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.action} at {self.created_at}'
