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
