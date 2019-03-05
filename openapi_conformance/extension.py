"""
This file contains workarounds and extensions built on top of
openapi_core, potentially things which could be merged into openapi_core
itself.
"""

# std
import contextlib
import copy
from collections import namedtuple
from unittest.mock import patch
from urllib.parse import unquote_plus

# 3rd party
from openapi_core import create_spec as _create_spec
from openapi_core.schema.media_types.models import MEDIA_TYPE_DESERIALIZERS
from openapi_core.schema.schemas.enums import SchemaFormat, SchemaType
from openapi_core.schema.schemas.exceptions import OpenAPISchemaError
from openapi_core.schema.schemas.models import Format, Schema
from openapi_core.validation.response.validators import ResponseValidator  # noqa
from ruamel.yaml import round_trip_load


def _schema_dict(schema):  # noqa
    """
    Convert a Schema object back to a dictionary which looks something
    like the original OpenAPI. However this isn't a complete conversion
    back to OpenAPI, since we only display property names to keep things
    simple.

    :param schema: openapi_core Schema object

    :return: Dict containing OpenAPI like description of this schema.
    """
    return {
        **({"type": schema.type.value} if schema.type else {}),
        **({"properties": list(schema.properties.keys())} if schema.properties else {}),
        **({"items": schema.items} if schema.items else {}),
        **({"format": schema.format} if schema.format else {}),
        **({"required": schema.required} if schema.required else {}),
        **({"default": schema.default} if schema.default else {}),
        **({"nullable": schema.nullable}),
        **({"enum": schema.enum} if schema.enum else {}),
        **({"deprecated": schema.deprecated}),
        **({"all_of": list(map(_schema_dict, schema.all_of))} if schema.all_of else {}),
        **({"one_of": list(map(_schema_dict, schema.one_of))} if schema.one_of else {}),
        **(
            {"additional_properties": schema.additional_properties}
            if schema.additional_properties
            else {}
        ),
        **({"min_items": schema.min_items} if schema.min_items is not None else {}),
        **({"max_items": schema.max_items} if schema.max_items is not None else {}),
        **({"min_length": schema.min_length} if schema.min_length is not None else {}),
        **({"max_length": schema.max_length} if schema.max_length is not None else {}),
        **({"pattern": schema.pattern} if schema.pattern is not None else {}),
        **({"pattern": schema.pattern} if schema.pattern else {}),
        **({"unique_items": schema.unique_items} if schema.unique_items else {}),
        **({"unique_items": schema.unique_items} if schema.unique_items else {}),
        **({"minimum": schema.minimum} if schema.minimum is not None else {}),
        **({"maximum": schema.maximum} if schema.maximum is not None else {}),
        **({"multiple_of": schema.multiple_of} if schema.multiple_of is not None else {}),
        **({"exclusive_minimum": schema.exclusive_minimum}),
        **({"exclusive_maximum": schema.exclusive_maximum}),
        **({"min_properties": schema.min_properties} if schema.min_properties is not None else {}),
        **({"max_properties": schema.max_properties} if schema.max_properties is not None else {}),
    }


@contextlib.contextmanager
def strict_bool():
    """
    """

    def strict_to_bool(x):
        if not isinstance(x, bool):
            raise OpenAPISchemaError(f"Expected bool but got {type(x)} -- {x}")
        return x

    original = Schema.DEFAULT_CAST_CALLABLE_GETTER
    patched = dict(original)
    patched[SchemaType.BOOLEAN] = strict_to_bool

    target = "openapi_core.schema.schemas.models.Schema.DEFAULT_CAST_CALLABLE_GETTER"
    with patch(target, patched):
        yield


@contextlib.contextmanager
def strict_str():
    """
    openapi_core unmarshals and validates strings by converting whatever
    is in the response to a str, and then validating that what we get is
    a str. This is of course rather silly, since lot's of things convert
    fine to a string. This means that we cannot validate string
    properties.

    To workaround this issue this function provides a means to patch
    openapi_core to use our own custom formatting for strings which
    strictly checks that a value is a string.

    For example...

      >>> with strict_str():
      ...   validator = ResponseValidator(...)
    """

    def strict_to_str(x):
        if not isinstance(x, str):
            raise OpenAPISchemaError(f"Expected str but got {type(x)} -- {x}")
        return x

    original = Schema.STRING_FORMAT_CALLABLE_GETTER
    patched = dict(original)
    patched[SchemaFormat.NONE] = Format(strict_to_str, lambda x: isinstance(x, str))

    target = "openapi_core.schema.schemas.models.Schema.STRING_FORMAT_CALLABLE_GETTER"
    with patch(target, patched):
        yield


_Value = namedtuple("Value", "schema value success")


@contextlib.contextmanager
def record_unmarshal():
    """
    Record calls to Shema.unmarshal so that when something fails we can
    actually show a nice error message to the user.
    """
    original = copy.deepcopy(Schema.unmarshal)
    log = []

    def unmarshal(self, value, custom_formatters=None):
        log.append(_Value(self, value, False))
        result = original(self, value, custom_formatters)
        log[-1] = _Value(log[-1].schema, log[-1].value, True)
        return result

    target = "openapi_core.schema.schemas.models.Schema.unmarshal"
    with patch(target, unmarshal):
        yield log


def create_spec(specification_path):
    """
    Helper wrapper around openapi_core.create_spec to enable creation of
    specs from other types

    :param specification_path: Path to the specification to load.

    :return: The created openapi_core Spec object.
    """
    with open(specification_path) as f:
        specification = _create_spec(round_trip_load(f))
    return specification


def operations(specification):
    """
    Get all operations of the specification.

    :param specification: openapi_core Spec object.

    :return: Generator yielding openapi_core Operation objects.
    """
    for operations in specification.paths.values():
        for operation in operations.operations.values():
            yield operation


def describe_operation(specification, operation):
    """
    Get a human readable string which describes an operation.

    :param specification: openapi_core Specification
    :param operation: openapi_core Operation

    :return: str representation of the operation.
    """
    return " ".join(
        (operation.http_method.upper(), specification.default_url + operation.path_name)
    )


def validate(validator, *args):
    """

    :param validator:
    :param args:
    :return:
    """
    with record_unmarshal() as log:
        with strict_str():
            with strict_bool():
                with patch_schema_validate():
                    with patch_media_type_deserializers():
                        result = validator.validate(*args)
                        try:
                            result.raise_for_errors()
                        except Exception as e:
                            e.unmarshal_log = log
                            raise e


@contextlib.contextmanager
def patch_schema_validate():
    """
    Patch Schema.validate to ensure that validation doesn't fail when
    we specify a custom format.

    openapi_core validation is a bit too strict when a custom format
    is specified. Basically our custom format unmarshals the value to
    the custom format we specify, however the validate function
    proceeds to check that the returned type of our custom unmarshal
    function is the correct type for the schema. However when
    specifying a custom format all bets should be off regarding types
    and we should just let the custom format determine if the value
    is valid or not.
    """
    original = copy.deepcopy(Schema.validate)

    def validate(self, value, custom_formatters=None):
        is_custom_formatted = self.format in (custom_formatters or {})
        return value if is_custom_formatted else original(self, value, custom_formatters)

    target = "openapi_core.schema.schemas.models.Schema.validate"
    with patch(target, validate):
        yield


@contextlib.contextmanager
def patch_media_type_deserializers():
    """
    Patch MEDIA_TYPE_DESERIALIZERS to provide a custom deserializer
    for application/x-www-form-urlencoded, perhaps there should be a
    nice way to provide custom deserializers in openapi_cor
    """

    def urldecode(qs):
        return dict(map(unquote_plus, x.split("=")) for x in qs.decode().split("&"))

    patched = {**MEDIA_TYPE_DESERIALIZERS, "application/x-www-form-urlencoded": urldecode}

    target = "openapi_core.schema.media_types.models.MEDIA_TYPE_DESERIALIZERS"
    with patch(target, patched):
        yield
