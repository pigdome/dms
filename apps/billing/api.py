"""
REST API สำหรับ Billing — ใช้ Django REST Framework
Endpoints:
  GET  /api/bills/        — รายการ bills ของ dormitory ของ token owner (paginated)
  GET  /api/bills/<id>/   — รายละเอียด bill พร้อม payment status

Tenant isolation: filter ด้วย dormitory ของ user ที่ถือ token เสมอ
Authentication: Token auth (rest_framework.authtoken)
"""
from rest_framework import serializers, generics
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from apps.billing.models import Bill, Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'amount', 'tmr_ref', 'paid_at', 'created_at']


class BillSerializer(serializers.ModelSerializer):
    payment = PaymentSerializer(read_only=True)
    room_number = serializers.CharField(source='room.number', read_only=True)
    month_display = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = [
            'id', 'invoice_number', 'room_number', 'month', 'month_display',
            'base_rent', 'water_amt', 'elec_amt', 'other_amt', 'total',
            'due_date', 'status', 'created_at', 'updated_at', 'payment',
        ]

    def get_month_display(self, obj):
        return obj.month.strftime('%B %Y') if obj.month else None


def _get_user_dormitory(request):
    """ดึง dormitory ของ user ที่ authenticated — ใช้ active_dormitory ถ้ามี, ไม่งั้นใช้ user.dormitory."""
    return getattr(request, 'active_dormitory', None) or getattr(request.user, 'dormitory', None)


class BillListAPIView(generics.ListAPIView):
    """
    GET /api/bills/ — รายการ bills ของ dormitory ของ user ที่ authenticate อยู่
    รองรับ query param: status=draft|sent|paid|overdue, month=YYYY-MM
    """
    serializer_class = BillSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # enforce tenant isolation — ดึงเฉพาะ bills ของ dormitory ตัวเอง
        dorm = _get_user_dormitory(self.request)
        if not dorm:
            return Bill.unscoped_objects.none()

        qs = Bill.unscoped_objects.filter(
            dormitory=dorm
        ).select_related('room', 'payment').order_by('-month', '-created_at')

        # optional filter by status
        status_param = self.request.query_params.get('status')
        if status_param and status_param in dict(Bill.Status.choices):
            qs = qs.filter(status=status_param)

        # optional filter by month (YYYY-MM)
        month_param = self.request.query_params.get('month')
        if month_param:
            try:
                year, month = month_param.split('-')
                qs = qs.filter(month__year=int(year), month__month=int(month))
            except (ValueError, AttributeError):
                pass

        return qs


class BillDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/bills/<id>/ — รายละเอียด bill พร้อม payment status
    enforce tenant isolation: bill ต้องอยู่ใน dormitory ของ user
    """
    serializer_class = BillSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # enforce tenant isolation — ห้ามเห็น bill ของ dormitory อื่น
        dorm = _get_user_dormitory(self.request)
        if not dorm:
            return Bill.unscoped_objects.none()
        return Bill.unscoped_objects.filter(
            dormitory=dorm
        ).select_related('room', 'payment')
