"""
This file contains workarounds and extensions built on top of
openapi_core, potentially things which could be merged into openapi_core
itself.
"""

# std
import contextlib
import copy
from collections import namedtuple
from functools import lru_cache
from pathlib import Path
from typing import IO
from unittest.mock import patch
from urllib.parse import unquote_plus

# 3rd party
from jsonschema.validators import RefResolver
from openapi_core.schema.media_types.models import MEDIA_TYPE_DESERIALIZERS
from openapi_core.schema.schemas.enums import SchemaFormat, SchemaType
from openapi_core.schema.schemas.exceptions import InvalidSchemaValue, OpenAPISchemaError
from openapi_core.schema.schemas.models import Format, Schema
from openapi_core.schema.schemas.registries import SchemaRegistry
from openapi_core.schema.specs.factories import SpecFactory
from openapi_core.schema.specs.models import Spec
from openapi_core.validation.response.validators import ResponseValidator  # noqa
from openapi_spec_validator import default_handlers
from openapi_spec_validator.validators import Dereferencer
from yaml import safe_load


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


CREATE_SPEC_SUPPORTED_TYPES = Path, str, IO, dict, Spec


class ObjectDefaultTypeSchemaRegistry(SchemaRegistry):
    """

    """

    def create(self, schema_spec):
        """

        :param schema_spec:

        :return:
        """
        schema_deref = self.dereferencer.dereference(schema_spec)
        schema_type = schema_deref.get("type", None)
        schema = super().create(schema_spec)
        if schema_type is None:
            schema.type = SchemaType.OBJECT
        return schema


class ObjectDefaultTypeSpecFactory(SpecFactory):
    """

    """

    @property
    @lru_cache()
    def schemas_registry(self):
        """
        :return:
        """
        return ObjectDefaultTypeSchemaRegistry(self.dereferencer)


def _create_spec(spec_dict, spec_url=""):
    """

    :param spec_dict:
    :param spec_url:

    :return:
    """
    spec_resolver = RefResolver(spec_url, spec_dict, handlers=default_handlers)
    dereferencer = Dereferencer(spec_resolver)
    spec_factory = ObjectDefaultTypeSpecFactory(dereferencer)
    return spec_factory.create(spec_dict, spec_url=spec_url)


def create_spec(specification):
    """
    Helper wrapper around openapi_core.create_spec to enable creation of
    specs from other types

    :param specification: Source for the specificaion, see
                          ``CREATE_SPEC_SUPPORTED_TYPES``

    :return: The created openapi_core Spec object.
    """
    if isinstance(specification, (Path, str)):
        with open(specification) as f:
            specification = _create_spec(safe_load(f))
    elif hasattr(specification, "read"):
        specification = _create_spec(safe_load(specification))
    elif isinstance(specification, dict):
        specification = _create_spec(specification)
    elif not isinstance(specification, Spec):
        raise TypeError(f"Expected one of {CREATE_SPEC_SUPPORTED_TYPES}, got {type(specification)}")

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

    def validate(self, value, custom_formatters=None):
        if value is None:
            if not self.nullable:
                raise InvalidSchemaValue(
                    "Null value for non-nullable schema of type {type}", value, self.type
                )
            return

        # type validation
        type_validator_callable = self.TYPE_VALIDATOR_CALLABLE_GETTER[self.type]
        if not type_validator_callable(value) and self.format not in custom_formatters:
            raise InvalidSchemaValue("Value {value} not valid type {type}", value, self.type.value)

        # structure validation
        validator_mapping = self.get_validator_mapping()
        validator_callable = validator_mapping[self.type]
        validator_callable(value, custom_formatters=custom_formatters)

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

    patched = dict(MEDIA_TYPE_DESERIALIZERS)
    patched["application/x-www-form-urlencoded"] = urldecode

    target = "openapi_core.schema.media_types.models.MEDIA_TYPE_DESERIALIZERS"
    with patch(target, patched):
        yield
