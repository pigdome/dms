"""Custom template tags and filters for core app."""
from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Allow dict lookup by variable key in templates: {{ my_dict|get_item:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
