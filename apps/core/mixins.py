"""
Core mixins สำหรับ:
1. Auto-audit logging บน critical models (AuditMixin)
2. Permission enforcement บน class-based views (OwnerRequiredMixin, StaffRequiredMixin, TenantScopeMixin)

AuditMixin: override save() และ delete() เพื่อบันทึก ActivityLog
พร้อม old_value / new_value ของ fields ที่เปลี่ยนแปลง

วิธีใช้ AuditMixin:
    class Bill(AuditMixin, TenantModelMixin):
        AUDIT_FIELDS = ['status', 'total', 'due_date']   # optional whitelist
        ...

วิธีใช้ Permission Mixins:
    class BillingSettingsView(OwnerRequiredMixin, View):  # owner/superadmin เท่านั้น
        ...
    class RoomListView(StaffRequiredMixin, View):         # owner/superadmin/staff เข้าได้
        ...

ถ้าไม่กำหนด AUDIT_FIELDS จะ capture ทุก concrete field ยกเว้น timestamps
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import models


# ---------------------------------------------------------------------------
# Permission Mixins สำหรับ Class-Based Views
# ---------------------------------------------------------------------------

class OwnerRequiredMixin(LoginRequiredMixin):
    """
    Mixin สำหรับ views ที่เฉพาะ owner หรือ superadmin เท่านั้นที่เข้าได้
    - Anonymous user → redirect to login (via LoginRequiredMixin)
    - Authenticated แต่ role ไม่ใช่ owner/superadmin → 403 PermissionDenied
    """
    # roles ที่อนุญาต
    _OWNER_ROLES = frozenset({'owner', 'superadmin'})

    def dispatch(self, request, *args, **kwargs):
        # ตรวจสอบ authentication ก่อน — anonymous user → redirect to login
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        # ตรวจ role ก่อน dispatch จริง — ป้องกัน 302 ที่เกิดจาก view handler
        # ผ่านไป handle_no_permission() โดยตรงถ้าไม่มีสิทธิ์ (raise PermissionDenied → 403)
        if request.user.role not in self._OWNER_ROLES:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin(LoginRequiredMixin):
    """
    Mixin สำหรับ views ที่ owner, superadmin, building_manager, และ staff เข้าได้
    แต่ tenant ไม่มีสิทธิ์
    - Anonymous user → redirect to login (via LoginRequiredMixin)
    - role == 'tenant' → 403 PermissionDenied
    """
    # building_manager สิทธิ์มากกว่า staff จึงควรผ่าน staff view ได้
    _STAFF_ROLES = frozenset({'owner', 'superadmin', 'building_manager', 'staff'})

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if response.status_code in (301, 302):
            return response
        if request.user.role not in self._STAFF_ROLES:
            raise PermissionDenied
        return response


class BuildingManagerRequiredMixin(LoginRequiredMixin):
    """
    Mixin สำหรับ views ที่ building_manager, owner, หรือ superadmin เข้าได้
    - staff และ tenant ไม่ผ่าน (403)
    - building_manager เห็นเฉพาะ buildings ที่ assign ให้ผ่าน managed_buildings
    - owner/superadmin เห็นได้ทุก building ใน dormitory

    วิธีใช้ใน view:
        class SomeView(BuildingManagerRequiredMixin, TenantScopeMixin, ListView):
            model = Building
            # get_queryset จะถูก scope โดย TenantScopeMixin แต่
            # สำหรับ building_manager ให้ call get_managed_buildings_qs() เพิ่มเติม

    helper method:
        get_managed_buildings_qs() — คืน queryset ของ Building ที่ user มีสิทธิ์เข้าถึง
    """
    _BUILDING_MANAGER_ROLES = frozenset({'owner', 'superadmin', 'building_manager'})

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if response.status_code in (301, 302):
            return response
        # staff และ tenant ไม่มีสิทธิ์เข้า building manager view
        if request.user.role not in self._BUILDING_MANAGER_ROLES:
            raise PermissionDenied
        return response

    def get_managed_buildings_qs(self):
        """
        คืน queryset ของ Building ที่ request.user มีสิทธิ์มองเห็น:
        - owner/superadmin: ทุก building ใน active dormitory
        - building_manager: เฉพาะ buildings ที่ assign ผ่าน managed_buildings
        """
        from apps.rooms.models import Building
        user = self.request.user
        if user.role in ('owner', 'superadmin'):
            dorm = getattr(self.request, 'active_dormitory', None) or user.dormitory
            if dorm:
                return Building.objects.filter(dormitory=dorm)
            return Building.objects.none()
        # building_manager — จำกัดเฉพาะ buildings ที่ assign ให้
        return user.managed_buildings.all()


class StaffPermissionRequiredMixin(LoginRequiredMixin):
    """
    I2: Mixin ที่ตรวจ StaffPermission สำหรับ views ที่ต้องการ permission เฉพาะ

    วิธีใช้:
        class BillListView(StaffPermissionRequiredMixin, View):
            permission_flag = 'can_view_billing'

    Roles ที่ผ่านทั้งหมดโดยอัตโนมัติ: owner, superadmin, building_manager
    Staff ต้องมี StaffPermission record ที่ permission_flag=True

    ถ้าไม่กำหนด permission_flag จะ fallback เป็น StaffRequiredMixin behavior (role check เท่านั้น)
    """
    permission_flag: str = ''

    # Roles ที่ผ่านทุก permission โดยไม่ต้อง check StaffPermission
    _BYPASS_ROLES = frozenset({'owner', 'superadmin', 'building_manager'})
    # Roles ที่ต้อง check StaffPermission
    _STAFF_ROLES = frozenset({'staff'})
    # Roles ที่ไม่มีสิทธิ์เลย
    _DENIED_ROLES = frozenset({'tenant'})

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if response.status_code in (301, 302):
            return response

        user = request.user
        role = getattr(user, 'role', None)

        # Tenant ไม่มีสิทธิ์เข้า staff views
        if role in self._DENIED_ROLES:
            raise PermissionDenied

        # Owner/superadmin/building_manager ผ่านทุก permission
        if role in self._BYPASS_ROLES:
            return response

        # Staff ต้อง check StaffPermission record
        if role in self._STAFF_ROLES and self.permission_flag:
            try:
                from apps.core.models import StaffPermission
                # BUG #3 fix: ต้อง filter dormitory ด้วยเสมอ
                # มิฉะนั้น staff ที่มี permission ใน dormitory A จะผ่าน check ของ dormitory B ได้
                # ซึ่งเป็น tenant isolation leak ที่อันตราย
                user_dormitory = getattr(request, 'active_dormitory', None) or getattr(user, 'dormitory', None)
                perm = StaffPermission.objects.get(user=user, dormitory=user_dormitory)
                if not getattr(perm, self.permission_flag, False):
                    raise PermissionDenied
            except StaffPermission.DoesNotExist:
                # ไม่มี StaffPermission record สำหรับ dormitory นี้ = ไม่มีสิทธิ์
                raise PermissionDenied

        return response


class TenantScopeMixin:
    """
    Mixin สำหรับ views ที่ต้อง enforce tenant isolation ใน queryset
    override get_queryset() เพื่อ filter ด้วย dormitory ของ user เสมอ

    วิธีใช้:
        class RoomListView(StaffRequiredMixin, TenantScopeMixin, ListView):
            model = Room
            # get_queryset() จะถูก filter dormitory อัตโนมัติ

    หรือสำหรับ model ที่ไม่มี dormitory FK ตรงๆ ให้ override get_dormitory_filter():
        def get_dormitory_filter(self):
            return {'floor__building__dormitory': self.get_active_dormitory()}
    """

    def get_active_dormitory(self):
        """ดึง active dormitory จาก request (จาก middleware หรือ user.dormitory)."""
        request = getattr(self, 'request', None)
        if request is None:
            return None
        return getattr(request, 'active_dormitory', None) or request.user.dormitory

    def get_dormitory_filter(self):
        """
        Return dict of filter kwargs สำหรับ tenant isolation
        Subclass ที่มี model structure ต่างออกไปควร override method นี้
        """
        dorm = self.get_active_dormitory()
        return {'dormitory': dorm} if dorm else {}

    def get_queryset(self):
        """Override get_queryset() เพื่อ enforce tenant scope เสมอ."""
        qs = super().get_queryset()
        dorm_filter = self.get_dormitory_filter()
        if dorm_filter:
            qs = qs.filter(**dorm_filter)
        return qs


# Fields ที่ไม่ต้องติดตามเพราะเปลี่ยนทุก save (จะทำให้ log รก)
_SKIP_FIELDS = frozenset({
    'created_at', 'updated_at',
})


def _serialize_value(value):
    """แปลง value ให้เป็น JSON-serializable (UUID, Decimal, date, etc.)."""
    import decimal
    import datetime
    import uuid

    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, decimal.Decimal):
        # normalize: ตัด trailing zeros ออก เช่น 3500.00 → 3500, 18.50 → 18.5
        # เพื่อให้ comparison old vs new ไม่เกิด false-diff
        return str(value.normalize())
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _snapshot(instance, fields: list[str]) -> dict:
    """ดึงค่าปัจจุบันของ fields ที่ระบุจาก model instance.

    DecimalField ที่ยังเป็น int/float ก่อน DB normalize จะถูกแปลงผ่าน Decimal
    เพื่อให้ consistent กับค่าที่ดึงจาก DB และหลีกเลี่ยง false-diff เช่น
    base_rent=3500 (int) vs Decimal('3500.00') จาก DB
    """
    import decimal

    # สร้าง map จาก attname → field object เพื่อเช็ค type
    decimal_fields = {
        f.attname
        for f in instance._meta.get_fields()
        if hasattr(f, 'attname') and isinstance(f, models.DecimalField)
    }

    data = {}
    for field_name in fields:
        try:
            raw = getattr(instance, field_name)
            # หาก field เป็น DecimalField และ value ยังเป็น int/float ให้ normalize
            if field_name in decimal_fields and not isinstance(raw, decimal.Decimal) and raw is not None:
                raw = decimal.Decimal(str(raw))
            data[field_name] = _serialize_value(raw)
        except AttributeError:
            pass
    return data


def _get_audit_fields(instance) -> list[str]:
    """หา field list ที่จะ audit — ใช้ AUDIT_FIELDS ถ้ากำหนด ไม่งั้น auto-detect."""
    if hasattr(instance, 'AUDIT_FIELDS') and instance.AUDIT_FIELDS:
        return list(instance.AUDIT_FIELDS)

    # Auto-detect: เอา concrete field ทุกอัน ยกเว้น skip list และ FK _id suffix
    fields = []
    for f in instance._meta.get_fields():
        if not isinstance(f, (models.Field,)):
            continue
        # ข้าม relation fields ที่ไม่มี column จริง (M2M, reverse FK)
        if not hasattr(f, 'attname'):
            continue
        name = f.attname  # attname = field name หรือ field_id สำหรับ FK
        if name in _SKIP_FIELDS:
            continue
        if name == 'id':
            continue
        fields.append(name)
    return fields


class AuditMixin:
    """
    Mixin สำหรับ Model ที่ต้องการ auto-audit log ทุก create/update/delete.

    การทำงาน:
    - save() ก่อน create → log action='create', new_value=snapshot
    - save() ก่อน update → compare old vs new, log เฉพาะ fields ที่เปลี่ยน
    - delete() → log action='delete', old_value=snapshot ก่อนลบ

    Thread-local user: ใช้ get_current_user() จาก threadlocal
    """

    def _get_audit_user(self):
        """ดึง user ปัจจุบันจาก thread-local (set โดย middleware)."""
        try:
            from apps.core.threadlocal import get_current_user
            return get_current_user()
        except ImportError:
            return None

    def _write_audit_log(self, *, action: str, old_value=None, new_value=None):
        """เขียน ActivityLog entry — เรียกได้จาก save() และ delete()."""
        from apps.core.models import ActivityLog

        user = self._get_audit_user()
        model_name = self.__class__.__name__
        record_id = str(self.pk) if self.pk else None

        # ดึง dormitory_id จาก instance ถ้ามี
        dorm_id = getattr(self, 'dormitory_id', None)

        # สร้าง log entry โดยไม่ผ่าน TenantManager (ใช้ unscoped_objects ถ้ามี)
        log = ActivityLog.__new__(ActivityLog)
        ActivityLog.__init__(log)
        log.user = user
        log.action = action
        log.model_name = model_name
        log.record_id = record_id
        log.old_value = old_value
        log.new_value = new_value
        log.detail = {
            'model': model_name,
            'record_id': record_id,
            'action': action,
        }
        if dorm_id:
            log.dormitory_id = dorm_id

        # บันทึกโดยตรงผ่าน unscoped_objects เพื่อหลีกเลี่ยง TenantManager filter
        log.save()

    def save(self, *args, **kwargs):
        # Lazy import เพื่อหลีกเลี่ยง circular import (models.py import mixins.py)
        from apps.core.models import ActivityLog

        audit_fields = _get_audit_fields(self)
        is_new = self._state.adding

        if is_new:
            # CREATE: บันทึก super ก่อน แล้วค่อย log new_value
            super().save(*args, **kwargs)
            new_snap = _snapshot(self, audit_fields)
            self._write_audit_log(
                action=ActivityLog.ACTION_CREATE,
                old_value=None,
                new_value=new_snap,
            )
        else:
            # UPDATE: ดึง old value จาก DB ก่อน save
            try:
                old_instance = self.__class__.unscoped_objects.get(pk=self.pk)
                old_snap = _snapshot(old_instance, audit_fields)
            except self.__class__.DoesNotExist:
                old_snap = {}

            super().save(*args, **kwargs)

            new_snap = _snapshot(self, audit_fields)

            # Log เฉพาะ fields ที่เปลี่ยนแปลงจริง
            changed_old = {k: v for k, v in old_snap.items() if new_snap.get(k) != v}
            changed_new = {k: new_snap[k] for k in changed_old}

            if changed_old:
                self._write_audit_log(
                    action=ActivityLog.ACTION_UPDATE,
                    old_value=changed_old,
                    new_value=changed_new,
                )

    def delete(self, *args, **kwargs):
        # Lazy import เพื่อหลีกเลี่ยง circular import
        from apps.core.models import ActivityLog

        audit_fields = _get_audit_fields(self)
        old_snap = _snapshot(self, audit_fields)

        # Log ก่อนลบจริงเพื่อ record_id ยังคงอยู่
        self._write_audit_log(
            action=ActivityLog.ACTION_DELETE,
            old_value=old_snap,
            new_value=None,
        )
        super().delete(*args, **kwargs)
