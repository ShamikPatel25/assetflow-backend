from django_filters import rest_framework as filters
from rest_framework.filters import OrderingFilter


class BaseFilterBackend(filters.DjangoFilterBackend):
    """Custom filter backend that passes the view into BaseFilterSet."""

    def get_filterset(self, request, queryset, view):
        filterset_class = self.get_filterset_class(view, queryset)
        if not filterset_class:
            return None
        kwargs = {
            "data": request.query_params,
            "queryset": queryset,
            "request": request,
        }
        if issubclass(filterset_class, BaseFilterSet):
            kwargs["view"] = view
        return filterset_class(**kwargs)


class BaseFilterSet(filters.FilterSet):
    """Base filterset that can access the current view."""

    def __init__(self, *args, **kwargs):
        self.view = kwargs.pop("view", None)
        super().__init__(*args, **kwargs)


class CustomOrderingFilter(OrderingFilter):
    """Ordering filter with alias support and sensible defaults."""

    def _build_ordering(self, params, view):
        ordering_fields = getattr(view, "ordering_fields", [])
        ordering_aliases = getattr(view, "ordering_aliases", {})
        result = []
        for field in params:
            clean = field.lstrip("-")
            if clean in ordering_aliases or clean in ordering_fields:
                prefix = "-" if field.startswith("-") else ""
                actual = ordering_aliases.get(clean, clean)
                result.append(f"{prefix}{actual}")
        return result if result else self.get_default_ordering(view)

    def get_ordering(self, request, queryset, view):
        params = request.query_params.getlist(self.ordering_param)
        if not params:
            return self.get_default_ordering(view)
        return self._build_ordering(params, view)
