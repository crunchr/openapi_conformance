# std
import json
from pathlib import Path

# 3rd party
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openapi_core.validation.request.validators import RequestValidator
from openapi_core.wrappers.mock import MockResponse

# openapi_conformance
from openapi_conformance import OpenAPIConformance, Strategies
from openapi_conformance.extension import describe_operation

DIR = Path(__file__).parent
st_conformance = Strategies()
# TODO : Probably useful to test multiple specifications, make this
#  also part of the parameterization
conformance = OpenAPIConformance(DIR / "data" / "petstore.yaml", None)


@pytest.mark.parametrize(
    "operation",
    conformance.operations,
    ids=[
        describe_operation(conformance.specification, x)
        for x in conformance.operations
        if True and False
    ],
)
def test_round_trip(operation):
    """
    Use OpenAPIConformance to generate a request for this operation,
    validate that the request conforms, then generate a response from
    the request OpenAPIConformance will then check that this conforms.
    """

    @given(st.data())
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow], max_examples=10)
    def check_conformance(data):
        def send_request(operation, request):
            RequestValidator(conformance.specification).validate(request).raise_for_errors()
            for status_code, response in operation.responses.items():
                for mimetype, schema in response.content.items():
                    response = data.draw(st_conformance.schema_values(schema.schema))
                    # TODO: Use mimetype to encode this
                    content = json.dumps(response).encode()
                    # TODO: Check what 'default' means
                    status_code = 500 if status_code == "default" else int(status_code)
                    return MockResponse(content, status_code)

        conformance.send_request = send_request
        conformance.check_operation_conformance(operation)

    check_conformance()
