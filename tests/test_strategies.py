# std
import operator
from unittest.mock import MagicMock

# 3rd party
import pytest
from hypothesis import given
from hypothesis import strategies as st

# openapi_conformance
from openapi_conformance.strategies import Strategies


def test_unsupported_format():
    """
    Check that a value error is raised when we come across a custom
    format that does not have an associated strategy.
    """
    schema = MagicMock(one_of=[], format="something")
    with pytest.raises(ValueError):
        Strategies().schema_values(schema).example()


@given(st.data())
def test_minimum_maximum(data):
    """
    Checks that Strategies.minimum and Strategies.maximum convert an
    exclusive minimum / maximum value to it's equivalent inclusive one.
    There is no way in hypothesis to give an exclusive min or max value
    to st.integers, so we have to simulate this ourselves.

    Here we check that the conversion from exclusive to inclusive works
    as expected by checking the property that an example drawn using
    the transformed extremes should be less than (or greater than) the
    exclusive extreme.

    :param data: Data strategy for interactively drawing examples.
    """
    which = data.draw(st.sampled_from([Strategies.minimum, Strategies.maximum]))

    exclusive_extreme = data.draw(st.integers())
    inclusive_extreme = which(exclusive_extreme, exclusive=True)

    key = "min" if which == Strategies.minimum else "max"
    op = operator.gt if which == Strategies.minimum else operator.lt
    kwargs = {f"{key}_value": inclusive_extreme}
    example = data.draw(st.integers(**kwargs))

    assert op(example, exclusive_extreme)


def test_multiple_of():
    """
    Check that the function returned from Strategies.is_multiple_of
    correctly determines if a value is a multiple or not.
    """
    assert Strategies.is_multiple_of(10)(20)
    assert not Strategies.is_multiple_of(3)(4)
