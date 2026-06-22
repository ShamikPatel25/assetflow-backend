from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.base import errors
from apps.base.errors import AFValidationError, AFDataIntegrityError
from apps.base.functions import get_user_display, extract_nested_fields


class BaseSerializer(serializers.Serializer):
    """Base serializer with field filtering and audit field display."""

    def __init__(self, *args, **kwargs):
        allowed_fields = kwargs.pop("allowed_fields", [])
        remove_fields = kwargs.pop("remove_fields", [])
        remove_audit_fields = kwargs.pop("remove_audit", False)

        self._allowed_field_map = extract_nested_fields(allowed_fields)
        self._remove_field_map = extract_nested_fields(remove_fields)

        super().__init__(*args, **kwargs)

        self._apply_allowed_fields()
        self._apply_removed_fields()
        if remove_audit_fields:
            self._strip_audit_fields()

    @property
    def is_fake(self):
        view = self.context.get("view")
        return getattr(view, "is_fake_view", False) if view else True

    @property
    def request(self):
        return self.context.get("request")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field_name in ("created_by", "updated_by"):
            if field_name in data:
                try:
                    data[field_name] = get_user_display(getattr(instance, field_name, None))
                except Exception:
                    pass
        return data

    def validate_serializer(self):
        if not self.is_valid(raise_exception=True):
            err_dict = dict(self.errors)
            field = list(err_dict.keys())[0]
            msg = f"{field.split('__')[0]} - {err_dict[field][0]}"
            raise AFValidationError(msg)
        return True, None

    @staticmethod
    def basic_fields(*args):
        return ("id",) + args

    @staticmethod
    def base_fields(*args):
        return (
            "id", "created_at", "updated_at", "created_by",
            "updated_by", "is_active", "is_deleted",
        ) + args

    # ── Private helpers ───────────────────────────────────────────

    def _apply_allowed_fields(self):
        if not self._allowed_field_map:
            return
        allowed_keys = set(BaseSerializer.basic_fields(*self._allowed_field_map.keys()))
        for name in list(self.fields):
            if name not in allowed_keys:
                self.fields.pop(name, None)
        for name, nested in self._allowed_field_map.items():
            if nested and name in self.fields:
                field = self.fields[name]
                nested_ser = field.child if isinstance(field, serializers.ListSerializer) else field
                if isinstance(nested_ser, BaseSerializer):
                    nested_ser._allowed_field_map = extract_nested_fields(nested)
                    nested_ser._apply_allowed_fields()

    def _apply_removed_fields(self):
        for name, nested in self._remove_field_map.items():
            if not nested:
                self.fields.pop(name, None)
                continue
            field = self.fields.get(name)
            if field is None:
                continue
            nested_ser = field.child if isinstance(field, serializers.ListSerializer) else field
            if isinstance(nested_ser, BaseSerializer):
                nested_ser._remove_field_map = extract_nested_fields(nested)
                nested_ser._apply_removed_fields()

    def _strip_audit_fields(self):
        for field_name in BaseSerializer.base_fields():
            if field_name == "id":
                if field_name in self.fields:
                    self.fields[field_name].read_only = False
                continue
            self.fields.pop(field_name, None)


class BaseModelSerializer(serializers.ModelSerializer, BaseSerializer):
    """Model serializer with UUID id, unique_together validation, and audit fields."""

    id = serializers.UUIDField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_deleted = serializers.BooleanField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)

    def is_valid(self, *, raise_exception=False):
        super().is_valid()
        is_violated = False
        if not self._errors:
            is_violated = self._check_unique_together()
        if self._errors:
            app_code = errors.RECORD_ALREADY_EXIST if is_violated else errors.DATA_VALIDATION_FAILED
            err_dict = dict(self.errors)
            field = list(err_dict.keys())[0]
            error_msg = err_dict[field]
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            raise AFValidationError(
                f"{field.split('__')[0]} - {error_msg}",
                app_code=app_code,
            )
        return not bool(self._errors)

    def _check_unique_together(self):
        unique_sets = getattr(self.Meta.model._meta, "unique_together", ())
        is_violated = False
        for field_set in unique_sets:
            lookup = {}
            for item in field_set:
                if item in self.validated_data:
                    val = self.validated_data[item]
                    key = f"{item}__iexact" if isinstance(val, str) else item
                    lookup[key] = val
            if not lookup or len(lookup) != len(field_set):
                continue
            try:
                obj = self.Meta.model.objects.get(**lookup)
                if not (self.instance and obj.id == self.instance.id):
                    err = ", ".join(lookup.keys())
                    msg = "Combined values should be unique" if len(lookup) > 1 else "Value should be unique"
                    self._errors[err] = [msg]
                    is_violated = True
            except ObjectDoesNotExist:
                pass
        return is_violated


class ReadOnlySerializer(BaseSerializer):
    """Serializer where all fields are read-only."""

    def get_fields(self):
        fields = super().get_fields()
        for field in fields.values():
            field.read_only = True
            field.required = False
        return fields


class ReadOnlyModelSerializer(BaseModelSerializer, ReadOnlySerializer):
    pass
