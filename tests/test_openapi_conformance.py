# 3rd party
from hypothesis import given

# openapi_conformance
from openapi_conformance import __version__
from openapi_conformance.strategies import Strategies


def test_version():
    assert __version__ == "0.1.0"


def test_strategy_generation():
    st = Strategies()

    @given(st.schema_values(None))
    def inner(schema_value):
        print()

    inner()
