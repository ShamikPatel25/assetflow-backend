import logging

from django.conf import settings
from django.db import transaction
from django.http import Http404
from rest_framework import viewsets, mixins, status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class BaseViewSet(viewsets.GenericViewSet):
    """
    Base viewset for all AssetFlow endpoints.

    - Restricts HTTP methods to get, post, put, delete (no patch).
    - Wraps create/update in transactions with audit fields.
    - Performs soft delete on destroy.
    - Catches unhandled exceptions safely.
    """

    http_method_names = ["get", "post", "put", "delete"]
    ordering = ("-created_at",)

    @property
    def is_fake_view(self):
        return getattr(self, "swagger_fake_view", False)

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(qs, "active"):
            return qs.active()
        return qs

    def get_serializer(self, *args, **kwargs):
        if "serializer_class" in kwargs:
            serializer_class = kwargs.pop("serializer_class")
        else:
            serializer_class = self.get_serializer_class()
        context = self.get_serializer_context()
        context.update({"request": self.request})
        if "context" not in kwargs:
            kwargs["context"] = {}
        kwargs["context"].update(context)
        return serializer_class(*args, **kwargs)

    def get_response_serializer(self, *args, **kwargs):
        if "serializer_class" not in kwargs:
            kwargs["serializer_class"] = self.serializer_class
        return self.get_serializer(*args, **kwargs)

    def perform_create(self, serializer):
        with transaction.atomic():
            return serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            return serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        """Soft delete: mark is_deleted=True instead of actual removal."""
        with transaction.atomic():
            instance.is_deleted = True
            instance.updated_by = self.request.user
            instance.save(update_fields=["is_deleted", "updated_by", "updated_at"])

    def unhandled_response(self, ex, function_name="NA"):
        if isinstance(ex, Http404):
            logger.error(
                "Object '%s' not found. function:%s",
                self.kwargs.get("pk"),
                function_name,
            )
            raise ex
        logger.exception(
            "Unhandled error in %s. Error: %s", function_name, str(ex)
        )
        msg = str(ex) if settings.DEBUG else "Something went wrong. Please try later."
        return Response({"message": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CRUDViewSet(
    BaseViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    """Full CRUD viewset: list, create, retrieve, update, soft-delete."""
    pass


class ReadOnlyViewSet(
    BaseViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """Read-only viewset: list and retrieve only."""
    pass
