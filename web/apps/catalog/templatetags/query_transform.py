# Lets pagination/filter links change just ONE query param (e.g. "page")
# while preserving every other active filter (?q=, ?source=, ?category=...).
# Used by templates/components/_pagination.html and any filter form across
# Home/Feed/news list pages.
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    request = context["request"]
    updated = request.GET.copy()
    for key, value in kwargs.items():
        if value is None:
            updated.pop(key, None)
        else:
            updated[key] = value
    return updated.urlencode()
