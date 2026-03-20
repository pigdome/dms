import threading

from contextlib import contextmanager

_thread_locals = threading.local()

def set_current_dormitory(dormitory):
    setattr(_thread_locals, 'dormitory', dormitory)

def get_current_dormitory():
    return getattr(_thread_locals, 'dormitory', None)

def clear_current_dormitory():
    if hasattr(_thread_locals, 'dormitory'):
        delattr(_thread_locals, 'dormitory')

@contextmanager
def dormitory_context(dormitory):
    """Context manager to set the current dormitory thread-locally."""
    old_dorm = get_current_dormitory()
    set_current_dormitory(dormitory)
    try:
        yield
    finally:
        if old_dorm is not None:
            set_current_dormitory(old_dorm)
        else:
            clear_current_dormitory()
