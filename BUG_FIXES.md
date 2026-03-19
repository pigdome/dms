# DMS Bug Fixes & Quick Wins

## 🐛 Bugs to Fix

### 1. Navigation Overlap on Forms (High Priority)

**Affected Pages:**
- `/notifications/parcels/` - Parcel logging form
- `/maintenance/` - Maintenance ticket list

**Problem:** Bottom navigation bar overlaps content

**Fix:** Add bottom padding to main content area

**File:** `templates/base.html`
```html
<!-- Current -->
<main class="flex-1 pt-14 pb-16">

<!-- Change to -->
<main class="flex-1 pt-14 pb-20">
```

Or add page-specific padding:

**File:** `templates/notifications/parcel_list.html`
```html
<!-- Add at start of block content -->
<div class="pb-20">
```

---

### 2. Missing Activity Logs (Medium Priority)

**Problem:** Dashboard shows "No recent activity" even after actions

**Solution:** Add ActivityLog creation on key actions

**File:** `apps/core/middleware.py` or individual views

**Example for Room Creation:**
```python
# In apps/rooms/views.py RoomCreateView.post()
from apps.core.models import ActivityLog

# After room.save():
ActivityLog.objects.create(
    dormitory=room.dormitory,
    user=request.user,
    action='room_created',
    detail={'room_id': room.pk, 'room_number': room.number},
)
```

**Key Actions to Log:**
- [ ] Room created/updated/deleted
- [ ] Meter reading saved
- [ ] Tenant added/updated
- [ ] Bill generated/paid
- [ ] Maintenance ticket created/status changed
- [ ] Parcel logged
- [ ] Broadcast sent

---

### 3. Duplicate Code: _SimpleForm Class (Low Priority)

**Problem:** `_SimpleForm` class duplicated in multiple view files

**Files:**
- `apps/rooms/views.py`
- `apps/tenants/views.py`
- (Possibly others)

**Fix:** Move to common utils

**File:** `apps/core/utils.py` (create new)
```python
from django import forms

class SimpleForm:
    """Minimal form shim for templates."""
    def __init__(self, data=None):
        self._data = data or {}

    def __getattr__(self, name):
        class Field:
            def __init__(self, val):
                self._val = val
                self.errors = []
            def value(self):
                return self._val
            def __str__(self):
                return str(self._val) if self._val is not None else ''
        return Field(self._data.get(name, ''))
```

Then update views:
```python
from apps.core.utils import SimpleForm

# Replace _SimpleForm with SimpleForm
```

---

### 4. Duplicate Code: staff_required Decorator (Low Priority)

**Problem:** `staff_required` decorator duplicated

**Fix:** Move to `apps/core/decorators.py` (create new)

**File:** `apps/core/decorators.py`
```python
from functools import wraps
from django.shortcuts import redirect

def staff_required(view_func):
    """Decorator: must be owner or staff (not a tenant user)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:login')
        if request.user.role == 'tenant':
            return redirect('tenant:home')
        return view_func(request, *args, **kwargs)
    return wrapper
```

Then update all views:
```python
from apps.core.decorators import staff_required
```

---

## 🚀 Quick Wins

### 1. Add Search to Rooms List (15 min)

**File:** `templates/rooms/list.html`

Add search form:
```html
<form method="get" class="flex gap-2 mb-4">
  <input type="text" name="q" value="{{ request.GET.q }}" 
         placeholder="Search room number..." 
         class="flex-1 px-4 py-2 border border-slate-200 rounded-lg">
  <button type="submit" class="px-4 py-2 bg-primary text-white rounded-lg">
    <i class="fa-solid fa-search"></i>
  </button>
</form>
```

**File:** `apps/rooms/views.py` RoomListView.get()
```python
search_query = request.GET.get('q', '')
if search_query:
    rooms = rooms.filter(number__icontains=search_query)
```

---

### 2. Add Export Button to Billing (10 min)

**File:** `templates/billing/list.html`

Add export button:
```html
<a href="?export=csv" 
   class="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700">
  <i class="fa-solid fa-download"></i> Export CSV
</a>
```

**File:** `apps/billing/views.py`
```python
def get(self, request):
    if request.GET.get('export') == 'csv':
        return self.export_csv(request)
    # ... existing logic

def export_csv(self, request):
    import csv
    from django.http import HttpResponse
    
    bills = self.get_queryset()  # Apply same filters
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bills.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Room', 'Month', 'Base Rent', 'Water', 'Electric', 'Total', 'Status'])
    for bill in bills:
        writer.writerow([
            bill.room.number,
            bill.month.strftime('%Y-%m'),
            bill.base_rent,
            bill.water_amt,
            bill.elec_amt,
            bill.total,
            bill.status,
        ])
    
    return response
```

---

### 3. Add Empty States with Illustrations (30 min)

**Example:** Empty rooms list

**File:** `templates/rooms/list.html`

Replace:
```html
{% else %}
<div class="bg-white rounded-xl border border-slate-100 shadow-sm p-8 text-center">
  <i class="fa-solid fa-door-open text-3xl text-slate-300 mb-3"></i>
  <p class="text-slate-500 font-medium">{% trans "No rooms found." %}</p>
  <a href="{% url 'rooms:create' %}" class="inline-block mt-3 text-primary text-sm font-semibold">
    {% trans "+ Add your first room" %}
  </a>
</div>
{% endif %}
```

With illustrated version:
```html
{% else %}
<div class="bg-white rounded-xl border border-slate-100 shadow-sm p-8 text-center">
  <img src="/static/illustrations/empty-rooms.svg" alt="" class="w-32 h-32 mx-auto mb-4">
  <h3 class="text-lg font-bold text-slate-700 mb-2">{% trans "No rooms yet" %}</h3>
  <p class="text-slate-500 mb-4">{% trans "Get started by adding your first room." %}</p>
  <a href="{% url 'rooms:create' %}" class="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white rounded-lg font-semibold hover:bg-primary/90">
    <i class="fa-solid fa-plus"></i>
    {% trans "Add Room" %}
  </a>
</div>
{% endif %}
```

---

### 4. Add Loading States to Forms (20 min)

**File:** `templates/base.html` (add JS)

```html
{% block extra_js %}
<script>
// Auto-disable form buttons on submit
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn && !submitBtn.disabled) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> ' + submitBtn.innerText;
      }
    });
  });
});
</script>
{% endblock %}
```

---

### 5. Add Dashboard Trend Indicators (25 min)

**File:** `apps/dashboard/views.py`

```python
# Add previous month comparison
from django.db.models import Sum
from datetime import timedelta

# Previous month income
from_date = now.replace(day=1) - timedelta(days=1)
prev_month_income = Bill.objects.filter(
    room__in=rooms_qs,
    status='paid',
    month__year=from_date.year,
    month__month=from_date.month,
).aggregate(total=Sum('total'))['total'] or 0

# Calculate trend
if prev_month_income > 0:
    income_trend = ((total_income - prev_month_income) / prev_month_income) * 100
else:
    income_trend = 100 if total_income > 0 else 0
```

**File:** `templates/dashboard/index.html`

```html
<div class="flex items-center gap-1 text-xs 
    {% if income_trend > 0 %}text-emerald-600
    {% elif income_trend < 0 %}text-red-600
    {% else %}text-slate-400{% endif %}">
  {% if income_trend > 0 %}
  <i class="fa-solid fa-arrow-trend-up"></i>
  {% elif income_trend < 0 %}
  <i class="fa-solid fa-arrow-trend-down"></i>
  {% endif %}
  <span>{{ income_trend|floatformat:1 }}%</span>
  <span class="text-slate-400">vs last month</span>
</div>
```

---

## 📝 Database Optimizations

### Add Indexes (10 min)

**File:** `apps/*/models.py`

Add indexes to frequently queried fields:

```python
# apps/billing/models.py
class Bill(models.Model):
    # ... existing fields
    class Meta:
        indexes = [
            models.Index(fields=['status', 'month']),
            models.Index(fields=['room', '-month']),
            models.Index(fields=['status']),
        ]

# apps/rooms/models.py
class Room(models.Model):
    # ... existing fields
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['floor', 'status']),
        ]

# apps/maintenance/models.py
class MaintenanceTicket(models.Model):
    # ... existing fields
    class Meta:
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['room', '-created_at']),
        ]
```

Then run:
```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 🔒 Security Improvements

### 1. Add Rate Limiting (30 min)

**Install:**
```bash
pip install django-axes
```

**File:** `config/settings.py`
```python
INSTALLED_APPS = [
    # ...
    'axes',
]

MIDDLEWARE = [
    # ...
    'axes.middleware.AxesMiddleware',
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_HANDLER = 'axes.handlers.cache.AxesCacheHandler'
```

---

### 2. Add Custom Error Pages (20 min)

**File:** `templates/404.html`
```html
{% extends "base.html" %}
{% load i18n %}

{% block content %}
<div class="min-h-[60vh] flex items-center justify-center">
  <div class="text-center">
    <h1 class="text-6xl font-bold text-slate-300 mb-4">404</h1>
    <p class="text-xl text-slate-600 mb-6">{% trans "Page not found" %}</p>
    <a href="{% url 'dashboard:index' %}" 
       class="px-6 py-3 bg-primary text-white rounded-lg font-semibold">
      {% trans "Go Home" %}
    </a>
  </div>
</div>
{% endblock %}
```

**File:** `templates/500.html`
```html
{% extends "base.html" %}
{% load i18n %}

{% block content %}
<div class="min-h-[60vh] flex items-center justify-center">
  <div class="text-center">
    <i class="fa-solid fa-triangle-exclamation text-6xl text-red-400 mb-4"></i>
    <h1 class="text-2xl font-bold text-slate-700 mb-2">{% trans "Something went wrong" %}</h1>
    <p class="text-slate-600 mb-6">{% trans "Please try again later." %}</p>
    <a href="{% url 'dashboard:index' %}" 
       class="px-6 py-3 bg-primary text-white rounded-lg font-semibold">
      {% trans "Go Home" %}
    </a>
  </div>
</div>
{% endblock %}
```

**File:** `config/urls.py`
```python
handler404 = 'django.views.defaults.page_not_found'
handler500 = 'django.views.defaults.server_error'
```

---

## ✅ Testing Checklist

Before deploying to production:

- [ ] Run all migrations
- [ ] Test login for all roles (superadmin, owner, staff, tenant)
- [ ] Test tenant isolation (owner1 cannot see owner2's data)
- [ ] Test payment webhook with TMR sandbox
- [ ] Test LINE notifications
- [ ] Test mobile responsive on real devices
- [ ] Run load test with 50+ concurrent users
- [ ] Backup database
- [ ] Set up monitoring (Sentry, health checks)
- [ ] Configure HTTPS/SSL
- [ ] Set up automated backups

---

*Generated: March 19, 2026*
