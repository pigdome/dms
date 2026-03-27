from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST


def landing_view(request):
    """SEO-optimized public landing page."""
    if request.user.is_authenticated:
        if request.user.role == 'tenant':
            return redirect('tenant:home')
        return redirect('dashboard:index')
    return render(request, 'landing.html')


def login_view(request):

    """Login page — redirects based on role."""
    if request.user.is_authenticated:
        if request.user.role == 'tenant':
            return redirect('tenant:home')
        return redirect('dashboard:index')

    from django.contrib.auth.forms import AuthenticationForm
    form = AuthenticationForm(request)

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            if user.role == 'tenant':
                return redirect('tenant:home')
            return redirect('dashboard:index')
        else:
            messages.error(request, _('Invalid username or password.'))

    return render(request, 'auth/login.html', {'form': form, 'next': request.GET.get('next', '')})


@require_POST
def logout_view(request):
    """Logout — POST only."""
    logout(request)
    messages.success(request, _('You have been logged out.'))
    return redirect('core:login')


@method_decorator(login_required, name='dispatch')
class SetupWizardView(View):
    """3-step setup wizard: dormitory info → rooms → billing settings."""

    def _get_step(self, request):
        return int(request.GET.get('step', request.POST.get('step', 1)))

    def get(self, request, *args, **kwargs):
        step = self._get_step(request)
        return render(request, 'core/setup_wizard.html', {
            'step': step,
            'form': _WizardForm(step),
        })

    def post(self, request, *args, **kwargs):
        step = self._get_step(request)

        if step == 1:
            return self._handle_step1(request)
        elif step == 2:
            return self._handle_step2(request)
        elif step == 3:
            return self._handle_step3(request)

        return redirect('core:setup_wizard')

    def _handle_step1(self, request):
        from apps.core.models import Dormitory
        name = request.POST.get('name', '').strip()
        address = request.POST.get('address', '').strip()
        if not name or not address:
            messages.error(request, _('Please fill in all required fields.'))
            return render(request, 'core/setup_wizard.html', {
                'step': 1,
                'form': _WizardForm(1, request.POST),
            })

        dorm, created = Dormitory.objects.get_or_create(
            name=name,
            defaults={'address': address}
        )
        if not created:
            dorm.address = address
            dorm.save()

        if not request.user.dormitory:
            request.user.dormitory = dorm
            request.user.save()

        return redirect('core:setup_wizard' + '?step=2')

    def _handle_step2(self, request):
        from apps.rooms.models import Building, Floor, Room
        dorm = request.user.dormitory
        if not dorm:
            return redirect('core:setup_wizard')

        building_name = request.POST.get('building_name', '').strip()
        num_floors = int(request.POST.get('num_floors', 0) or 0)
        rooms_per_floor = int(request.POST.get('rooms_per_floor', 0) or 0)
        default_rent = request.POST.get('default_rent', 0) or 0

        if building_name and num_floors > 0 and rooms_per_floor > 0:
            building, _ = Building.objects.get_or_create(dormitory=dorm, name=building_name)
            for floor_num in range(1, num_floors + 1):
                floor, _ = Floor.objects.get_or_create(building=building, number=floor_num)
                for room_num in range(1, rooms_per_floor + 1):
                    room_number = f"{floor_num}{str(room_num).zfill(2)}"
                    Room.objects.get_or_create(
                        floor=floor,
                        number=room_number,
                        defaults={'base_rent': default_rent}
                    )

        return redirect('core:setup_wizard' + '?step=3')

    def _handle_step3(self, request):
        from apps.billing.models import BillingSettings
        dorm = request.user.dormitory
        if not dorm:
            return redirect('core:setup_wizard')

        settings, _ = BillingSettings.objects.get_or_create(dormitory=dorm)
        settings.elec_rate = request.POST.get('elec_rate', 7.00)
        settings.water_rate = request.POST.get('water_rate', 18.00)
        settings.bill_day = int(request.POST.get('bill_day', 1))
        settings.grace_days = int(request.POST.get('grace_days', 5))
        settings.save()

        messages.success(request, _('Setup completed successfully!'))
        return redirect('dashboard:index')


@login_required
@require_POST
def theme_toggle_view(request):
    """Toggle user theme between light and dark."""
    from apps.core.models import CustomUser
    user = request.user
    user.theme = CustomUser.Theme.DARK if user.theme == CustomUser.Theme.LIGHT else CustomUser.Theme.LIGHT
    user.save(update_fields=['theme'])
    return redirect(request.POST.get('next') or request.META.get('HTTP_REFERER') or 'dashboard:index')


@login_required
@require_POST
def property_switch_view(request):
    """Switch the active dormitory context for staff/owner users.

    Validates that the requested dormitory is one the user belongs to before
    writing it to the session.  Redirects back to the referring page.
    """
    from apps.core.models import Dormitory, UserDormitoryRole

    dormitory_id = request.POST.get('dormitory_id')
    if dormitory_id:
        try:
            dorm = Dormitory.objects.get(
                pk=dormitory_id,
                userdormitoryrole__user=request.user,
            )
            request.session['active_dormitory_id'] = str(dorm.pk)
        except Dormitory.DoesNotExist:
            messages.error(request, _('You do not have access to that property.'))

    return redirect(request.POST.get('next') or 'dashboard:index')


class _WizardForm:
    """Simple wrapper to pass POST data back to template."""
    def __init__(self, step, data=None):
        self.step = step
        self._data = data or {}

    def __getattr__(self, name):
        class _Field:
            def __init__(self, val):
                self._val = val
                self.errors = []
            def value(self):
                return self._val
        return _Field(self._data.get(name, ''))
