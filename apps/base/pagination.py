from rest_framework.pagination import PageNumberPagination


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        pagination = request.query_params.get("pagination", "1")
        if pagination == "0":
            return None
        return super().paginate_queryset(queryset, request, view)

    def get_schema_operation_parameters(self, view):
        params = super().get_schema_operation_parameters(view)
        params.append({
            "name": "pagination",
            "required": False,
            "in": "query",
            "description": "Set to 0 to disable pagination and return all records.",
            "schema": {"type": "string", "enum": ["0"]},
        })
        return params
