from apps.core.models import Dormitory


class ActiveDormitoryMiddleware:
    """Set request.active_dormitory based on the session-selected property.

    For authenticated staff/owner users, respects ``session['active_dormitory_id']``
    so they can switch between their properties without changing their account's
    default dormitory.  Falls back to ``request.user.dormitory`` when no session
    key is present.

    Tenant users always resolve via their active lease's dormitory (no switching).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_dormitory = self._resolve(request)
        
        from apps.core.threadlocal import set_current_dormitory, clear_current_dormitory
        set_current_dormitory(request.active_dormitory)
        try:
            response = self.get_response(request)
        finally:
            clear_current_dormitory()
        return response

    @staticmethod
    def _resolve(request):
        if not request.user.is_authenticated:
            return None

        if request.user.role == 'tenant':
            try:
                profile = request.user.tenant_profile
                return profile.dormitory
            except Exception:
                return request.user.dormitory

        dormitory_id = request.session.get('active_dormitory_id')
        if dormitory_id:
            try:
                return Dormitory.objects.get(
                    pk=dormitory_id,
                    userdormitoryrole__user=request.user,
                )
            except Dormitory.DoesNotExist:
                # Session value is stale or user lost access — clear it
                del request.session['active_dormitory_id']

        return request.user.dormitory
