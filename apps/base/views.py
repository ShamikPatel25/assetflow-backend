import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import NotFound
from rest_framework import viewsets, mixins, status
from rest_framework.response import Response
from apps.audit.services import log_action

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

    def get_object(self):
        try:
            return super().get_object()
        except (Http404, ValueError, ValidationError):
            model_class = getattr(self, "queryset", self.get_queryset()).model
            model_name = model_class._meta.verbose_name.title()
            raise NotFound({"message": f"{model_name} not found."})

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
            instance = serializer.save(created_by=self.request.user)
            
            log_action(
                user=self.request.user,
                action="CREATE",
                module=instance._meta.model_name.upper(),
                object_type=instance._meta.object_name,
                object_id=instance.id,
                object_repr=str(instance),
                request=self.request,
            )
            return instance

    def perform_update(self, serializer):
        with transaction.atomic():
            instance = serializer.save(updated_by=self.request.user)
            
            log_action(
                user=self.request.user,
                action="UPDATE",
                module=instance._meta.model_name.upper(),
                object_type=instance._meta.object_name,
                object_id=instance.id,
                object_repr=str(instance),
                request=self.request,
            )
            return instance

    def perform_destroy(self, instance):
        """Soft delete: mark is_deleted=True instead of actual removal."""
        with transaction.atomic():
            instance.is_deleted = True
            instance.updated_by = self.request.user
            instance.save(update_fields=["is_deleted", "updated_by", "updated_at"])

            log_action(
                user=self.request.user,
                action="DELETE",
                module=instance._meta.model_name.upper(),
                object_type=instance._meta.object_name,
                object_id=instance.id,
                object_repr=str(instance),
                request=self.request,
            )

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
    
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
            filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
            
            model_class = getattr(self, "queryset", self.get_queryset()).model
            model_name = model_class._meta.verbose_name.title()
            
            try:
                exists = model_class._default_manager.filter(**filter_kwargs).exists()
            except (ValidationError, ValueError):
                exists = False
                
            if exists:
                return Response(
                    {"message": f"{model_name} is already deleted."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response(
                {"message": f"{model_name} not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        model_name = instance._meta.verbose_name.title()
        self.perform_destroy(instance)
        return Response(
            {"message": f"{model_name} deleted successfully."},
            status=status.HTTP_200_OK
        )


class ReadOnlyViewSet(
    BaseViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """Read-only viewset: list and retrieve only."""
