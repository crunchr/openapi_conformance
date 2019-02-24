"""
This file contains workarounds and extensions built on top of
openapi_core, potentially things which could be merged into openapi_core
itself.
"""

# std
import contextlib
import copy
from collections import namedtuple
from pathlib import Path
from typing import IO
from unittest.mock import patch

# 3rd party
from openapi_core import create_spec as _create_spec
from openapi_core.schema.schemas.enums import SchemaFormat
from openapi_core.schema.schemas.exceptions import OpenAPISchemaError
from openapi_core.schema.schemas.models import Format, Schema
from openapi_core.schema.specs.models import Spec
from openapi_core.validation.response.validators import ResponseValidator  # noqa
from toolz import identity
from yaml import safe_load


def _schema_dict(schema):
    """
    Convert a Schema object back to a dictionary which looks something
    like the original OpenAPI. However this isn't a complete conversion
    back to OpenAPI, since we only display property names to keep things
    simple.

    :param schema: openapi_core Schema object

    :return: Dict containing OpenAPI like description of this schema.
    """

    def attr_if(attr, compare=bool, transform=identity):
        return {transform(getattr(schema, attr)) if compare(getattr(schema, attr)) else {}}

    def is_not_none(x):
        return x is not None

    return {
        **attr_if("type"),
        **attr_if("items"),
        **attr_if("format"),
        **attr_if("required"),
        **attr_if("default"),
        **attr_if("nullable"),
        **attr_if("enum"),
        **attr_if("deprecated"),
        **attr_if("all_of"),
        **attr_if("one_of"),
        **attr_if("additional_properties"),
        **attr_if("unique_items"),
        **attr_if("exclusive_minimum"),
        **attr_if("exclusive_maximum"),
        **attr_if("min_items", is_not_none),
        **attr_if("max_items", is_not_none),
        **attr_if("min_length", is_not_none),
        **attr_if("max_length", is_not_none),
        **attr_if("pattern", is_not_none),
        **attr_if("minimum", is_not_none),
        **attr_if("maximum", is_not_none),
        **attr_if("multiple_of", is_not_none),
        **attr_if("min_properties", is_not_none),
        **attr_if("max_properties", is_not_none),
        **attr_if("properties", bool, lambda x: list(map(_schema_dict, x))),
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


def raise_verbose_exception(e, log):
    """
    Create a new exception with additional information about which
    value and schema failed (or if the failure didn't occur because of
    an incorrect value the last successfully parsed value and schema)
    because the openapi_core error messages can be a little cryptic.

    :param e: Original exception.
    :param log: Log of the calls to unmarshal.
    """
    if log:
        schema, value = _schema_dict(log[-1].schema), log[-1].value
        if log[-1].success:
            msg = (
                f"Response does not conform to schema, the last successfully "
                f"unmarshalled schema was {schema} with value {value}."
            )
        else:
            msg = f"{value} does not conform to the schema {schema}."
        raise type(e)(msg) from e
    else:
        raise e


CREATE_SPEC_SUPPORTED_TYPES = Path, str, IO, dict, Spec


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
