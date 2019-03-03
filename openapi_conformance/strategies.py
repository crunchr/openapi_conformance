# std
import base64
from collections import namedtuple
from datetime import datetime
from functools import partial
from urllib.parse import quote_plus

# 3rd party
from hypothesis import strategies as st
from openapi_core.schema.schemas.enums import SchemaType
from toolz import curry, keyfilter, unique, valmap

ParameterValue = namedtuple("ParameterValue", "parameter value")


@st.composite
def st_filtered_containers(draw, container):
    """
    Generates a new container from container that contains, 0 or more
    (up to len(container)) items from the original.

    This strategy shrinks towards 0 items in the returned container.

    :param draw: Callable to draw examples from other strategies.
    :param container: The container to filter.

    :return: New container containing 0, some, or all items from
             container.
    """
    result = draw(st.sets(st.sampled_from(list(container)), max_size=len(container)))
    return type(container)(result)


@st.composite
def st_hostnames(draw):
    """

    :param draw:

    :return:
    """
    return draw(
        st.from_regex(r"(?!-)[a-z0-9-]{1,63}(?<!-)$").filter(lambda x: len(x) and len(x) < 253)
    )


@st.composite
def st_uris(draw):
    """

    :param draw:

    :return:
    """
    scheme = draw(st.sampled_from(("ftp", "http", "file", "custom")))

    userinfo = query = fragment = password = port = ""

    if draw(st.booleans()):  # userinfo
        username = quote_plus(draw(st.text()))
        if draw(st.booleans()):  # password
            password = ":" + quote_plus(draw(st.text()))
        userinfo = f"{username}{password}"
    host = draw(st_hostnames())
    if draw(st.booleans()):  # port
        port = f":{draw(st.integers(min_value=0, max_value=65535))}"
    authority = f"//{userinfo}{host}{port}"

    if draw(st.booleans()):  # query
        pass

    if draw(st.booleans()):  # fragment
        pass

    st_path_part = st.text(min_size=1).map(quote_plus)
    st_path_parts = st.lists(st_path_part, min_size=1)
    path_parts = draw(st_path_parts)
    path = "/".join(path_parts)

    return f"{scheme}:{authority}{path}{query}{fragment}"


def instance_composite(fn):
    """
    Wrapper around st.composite that can be used on instance methods.

    When using st.composite decorator on an instance methods hypothesis
    flips the self and draw parameters, meaning you have to define your
    composite strategies like so...

        >>> class Strategies:
        ...   @st.composite
        ...   def things(draw, self):
        ...      pass

    Which is quite unusual. With this decorator we ensure that we can
    define our instance methods in the usual way, e.g.

        >>> class Strategies:
        ...   @instance_composite
        ...   def things(self, draw):
        ...     pass

    :param fn: The function to convert to an instance composite
               strategy.

    :return: Decorated function.
    """

    @st.composite
    def inner(*args, **kwargs):
        return fn(args[1], args[0], *args[2:], **kwargs)

    return inner


class Strategies:
    """
    Various strategies for generating values that are part of an open
    api specification schema.
    """

    def __init__(self, format_strategies=None):
        """
        Initialise this instance.

        :param format_strategies: Dictionary providing strategies for
                                  generating data for various formats.
                                  These strategies take the schema being
                                  generated as a parameter.
        """
        self._format_strategies = format_strategies or {}

    def format_strategies(self, schema):
        """

        :param schema:

        :return:
        """
        min_max_size = dict(min_size=schema.min_length or 0, max_size=schema.max_length)
        return {
            **self._format_strategies,
            "email": st.emails(),
            "uuid": st.uuids().map(str),
            "uri": st_uris(),
            "uriref": st_uris(),
            "hostname": st_hostnames(),
            "date": st.dates().map(str),
            "date-time": st.datetimes().map(datetime.isoformat),
            "binary": st.binary(**min_max_size),
            "byte": st.binary(**min_max_size).map(base64.encodebytes),
            "int32": self.numbers(st_base=st.integers, schema=schema),
            "int64": self.numbers(st_base=st.integers, schema=schema),
            "float": self.numbers(st_base=st.floats, schema=schema),
            "double": self.numbers(st_base=st.floats, schema=schema),
        }

    def _strategy_for_schema(self, schema):
        """
        Get the hypothesis strategy which can be used to generate values for
        the given schema.`

        :param schema: openapi_core Schema to generate values for.

        :return: Hypothesis strategy that generates values for schema.
        """
        format_strategies = self.format_strategies(schema)

        if schema.format and schema.format not in format_strategies:
            raise ValueError(f"unsupported format {schema.format}")

        if schema.format in format_strategies:
            result = format_strategies[schema.format]
        else:
            result = {
                SchemaType.ANY: self.objects,
                SchemaType.INTEGER: partial(self.numbers, st_base=st.integers),
                SchemaType.NUMBER: partial(self.numbers, st_base=st.floats),
                SchemaType.STRING: self.strings,
                SchemaType.BOOLEAN: lambda *_, **__: st.booleans(),
                SchemaType.ARRAY: self.arrays,
                SchemaType.OBJECT: self.objects,
            }[schema.type](schema=schema)

        return result

    @staticmethod
    def is_multiple_of(multiple_of):
        """

        :param multiple_of:
        :return:
        """

        @curry
        def is_multiple_of(n, x):
            return not (x % n)

        return is_multiple_of(multiple_of)

    @staticmethod
    def minimum(value, exclusive):
        """

        :param value:
        :param exclusive:
        :param is_int:

        :return:
        """
        return (value or 0) + exclusive

    @staticmethod
    def maximum(value, exclusive):
        """

        :param value:
        :param exclusive:
        :param is_int:

        :return:
        """
        return None if value is None else (value - exclusive)

    @instance_composite
    def numbers(self, draw, st_base, schema):
        """
        Generate a number that conforms to the given schema.

        :param draw: Callable to draw examples from other strategies.
        :param st_base: Base strategy to use for drawing a number (e.g.
                        st.integers or st.floats)
        :param schema: The schema we are generating values for.

        :return: A float or int depending on base which conforms to the
                 given schema.
        """
        numbers = st_base(
            self.minimum(schema.minimum, schema.exclusive_minimum),
            self.maximum(schema.maximum, schema.exclusive_maximum),
            **dict(exclude_min=schema.exclusive_minimum, exclude_max=schema.exclusive_maximum)
            if st_base == st.floats
            else {},
        )
        if schema.multiple_of:
            numbers = numbers.filter(self.is_multiple_of(schema.multiple_of))

        return draw(numbers)

    @instance_composite
    def strings(self, draw, schema):
        """
        Generate some text that conforms to the given schema.

        :param draw: Callable to draw examples from other strategies.
        :param schema: The schema we are generating values for.

        :return: str which conforms to the given schema.
        """
        min_max = dict(min_size=schema.min_length or 0, max_size=schema.max_length)

        if schema.enum:
            strategy = st.sampled_from(schema.enum)
        elif schema.pattern:
            strategy = st.from_regex(schema.pattern)
        else:
            strategy = st.text(**min_max)

        return draw(strategy)

    @instance_composite
    def arrays(self, draw, schema):
        """
        Generate an array of other schema values that conform to the
        items schema.

        :param draw: Callable to draw examples from other strategies.
        :param schema: The schema we are generating values for.

        :return: list whose items are schema values that conform to the
                 schemas defined in schema.items.
        """
        items = draw(
            st.lists(
                self._strategy_for_schema(schema.items),
                min_size=schema.min_items or 0,
                max_size=schema.max_items,
            )
        )
        return unique(items) if schema.unique_items else items

    @instance_composite
    def objects(self, draw, schema):
        """
        Generate an object which conforms to the given schema.

        :param draw: Callable to draw examples from other strategies.
        :param schema: The schema we are generating values for.

        :return: Dictionary where the keys conform to the schema.
        """
        result = {}
        for schema in schema.all_of or [schema]:
            required = set(schema.required)
            optional = draw(st_filtered_containers(set(schema.properties) - required))
            properties = keyfilter(lambda x: x in required | optional, schema.properties)
            mapping = valmap(self._strategy_for_schema, properties)
            result = {**result, **draw(st.fixed_dictionaries(mapping))}

            # TODO: Additional parameters

        return result

    @instance_composite
    def schema_values(self, draw, schema):
        """
        Generate a value which conforms to the given schema.

        :param draw: Callable to draw examples from other strategies.
        :param schema: The schema we are generating values for.

        :return: A value which conforms to the given schema.
        """
        if schema:
            if schema.one_of:
                return draw(st.one_of(map(self._strategy_for_schema, schema.one_of)))
            else:
                return draw(self._strategy_for_schema(schema))

    @instance_composite
    def parameter_lists(self, draw, parameters):
        """
        Generate a list of parameters to send to a particular endpoint.

        :param draw: Callable to draw examples from other strategies.
        :param parameters: The parameters to generate values for.

        :return: list of ParameterValue objects which describe the
                 parameter and generated value.
        """
        return [
            ParameterValue(param, draw(self.schema_values(param.schema)))
            for param in parameters.values()
        ]
