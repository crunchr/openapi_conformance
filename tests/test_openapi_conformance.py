# std
import json
import os
from pathlib import Path
from urllib.parse import urlparse

# 3rd party
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openapi_core.schema.schemas.models import Format
from openapi_core.wrappers.mock import MockResponse

# openapi_conformance
from openapi_conformance import OpenAPIConformance, Strategies
from openapi_conformance.extension import describe_operation

DIR = Path(__file__).parent
st_conformance = Strategies()


def always_valid(x):
    return True


format_strategies = {"custom": st.integers()}


format_unmarshallers = {
    "uri": Format(urlparse, always_valid),
    "uriref": Format(urlparse, always_valid),
    "custom": Format(int, lambda x: isinstance(x, int)),
}


conformances = [
    (
        entry.name,
        OpenAPIConformance(
            directory / entry.name,
            None,
            format_unmarshallers=format_unmarshallers,
            format_strategies=format_strategies,
        ),
    )
    for directory in [DIR / "data"]
    for entry in os.scandir(directory)
]


filenames_conformances_operations = [
    (filename, conformance, operation)
    for filename, conformance in conformances
    for operation in conformance.operations
]


@pytest.mark.parametrize(
    "filename,conformance,operation",
    filenames_conformances_operations,
    ids=[
        f"{ filename} : { describe_operation(conformance.specification, operation)}"
        for filename, conformance, operation in filenames_conformances_operations
    ],
)
def test_round_trip(filename, conformance, operation):
    """
    Use OpenAPIConformance to generate a request for this operation,
    validate that the request conforms, then generate a response from
    the request OpenAPIConformance will then check that ths conforms.
    """

    @given(st.data())
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow], max_examples=10)
    def check(data):
        def generate_response(operation, request):
            """
            Generate the response for a given request.

            :param operation: The operation being requested.
            :param request: The request object.

            :return: MockResponse object containing the response data
                     status_code and mime_type.
            """
            st_responses = st.sampled_from(list(operation.responses.items()))
            status_code, response_definition = data.draw(st_responses)
            status_code = 500 if status_code == "default" else int(status_code)

            if response_definition.content:
                st_contents = st.sampled_from(list(response_definition.content.items()))
                mime_type, contents = data.draw(st_contents)
                response = data.draw(st_conformance.schema_values(contents.schema))
                content = json.dumps(response).encode()
            else:
                content = b""
                mime_type = "application/json"

            return MockResponse(content, status_code, mime_type)

        conformance.send_request = generate_response
        conformance.check_operation(operation)

    check()
