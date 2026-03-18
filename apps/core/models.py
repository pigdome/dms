from django.contrib.auth.models import AbstractUser
from django.db import models


class Dormitory(models.Model):
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
    class Role(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Superadmin'
        OWNER = 'owner', 'Owner'
        STAFF = 'staff', 'Staff'
        TENANT = 'tenant', 'Tenant'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TENANT)
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
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='dormitory_memberships')
    dormitory = models.ForeignKey(Dormitory, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=CustomUser.Role.choices, default=CustomUser.Role.STAFF)
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = [('user', 'dormitory')]

    def __str__(self):
        return f'{self.user} @ {self.dormitory} ({self.role})'


class ActivityLog(models.Model):
    dormitory = models.ForeignKey(Dormitory, on_delete=models.CASCADE, related_name='activity_logs')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=200)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.action} at {self.created_at}'
