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
