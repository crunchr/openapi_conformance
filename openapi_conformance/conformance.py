# std
import json
from urllib.parse import urlencode

# 3rd party
from hypothesis import given
from hypothesis import strategies as st
from openapi_core.schema.parameters.enums import ParameterLocation
from openapi_core.validation.request.validators import RequestValidator
from openapi_core.validation.response.validators import ResponseValidator
from openapi_core.wrappers.mock import MockRequest

# openapi_conformance
from openapi_conformance.extension import create_spec, operations, validate
from openapi_conformance.strategies import Strategies


class OpenAPIConformance:
    """

    """

    def __init__(
        self,
        specification,
        send_request,
        format_strategies=None,
        format_unmarshallers=None,
        mime_type_decoders=None,
    ):
        """
        The actual request is made by the send_request callable,
        which takes the following parameters...

        :param specification: Specification to check conformance for,
                              or file or path where the specification
                              can be loaded, or a dict containing the
                              specification.
        :param send_request: Callable to invoke the implementation,
                             takes the following parameters...

            - request:      openapi_core BaseOpenAPIRequest object
                            containing information about the http
                            method, path etc.
            - parameters:   openapi_core Parameters object containing
                            information about the parameters to send
                            with the request.
            - request_body: data to send in the request body,
                            send_request is responsible for serializing
                            this data for the particular mime type
                            associated with the body.

            send_request should return an instance of a type which
            implements ``BaseOpenAPIResponse`` containing the response
            from the implementation.

        :param format_strategies: dictionary with strategies for various
                                  formats to provide custom data
                                  generation.
        :param format_unmarshallers: dictionary with callables which can
                                     be used to unmarshal values when a
                                     custom format is given. The key
                                     should be the format name, with the
                                     value being an openapi_core.schema.schemas.models.Format
                                     object.
        """
        self.specification = create_spec(specification)
        self.send_request = send_request
        self.st = Strategies(format_strategies)
        self.format_unmarshallers = format_unmarshallers
        self.mime_type_decoders = {
            "application/json": lambda data: json.dumps(data).encode(),
            "application/x-www-form-urlencoded": lambda data: urlencode(data).encode(),
            **(mime_type_decoders or {}),
        }

    @property
    def operations(self):
        """
        :return: All the operations in the specification.
        """
        return operations(self.specification)

    def check_response(self, request, response):
        """
        Check that a given response conforms to the specified valid
        responses.

        :param request: openapi_core BaseOpenAPIRequest object
        :param response: openapi_core BaseOpenAPIResponse object
        """
        request_validator, response_validator = (
            validator_type(self.specification, self.format_unmarshallers)
            for validator_type in (RequestValidator, ResponseValidator)
        )
        validate(request_validator, request)
        validate(response_validator, request, response)

    def check_operation(self, operation):
        """
        Check that the implementation of a given operation conforms to
        the specification. If the implementation doesn't conform to the
        specification then an Exception is raised.

        :param operation: openapi_core Operation object
        """

        @given(st.data())
        def do_test(data):

            if operation.parameters:
                parameters = data.draw(self.st.parameter_lists(operation.parameters))
            else:
                parameters = None

            if operation.request_body:
                mime_type, content = data.draw(
                    st.sampled_from(list(operation.request_body.content.items()))
                )
                request_body = data.draw(self.st.schema_values(content.schema))
            else:
                mime_type = "application/json"
                request_body = None

            request, response = self._make_request(operation, parameters, request_body, mime_type)
            self.check_response(request, response)

        do_test()

    def check(self):
        """
        Check that an implementation conforms to the given
        specification.

        If the implementation doesn't conform to the specification then
        an Exception is raised.

        :param specification: openapi_core` Spec object
        :param send_request: Callable to invoke the implementation.
        """
        for operation in self.operations:
            self.check_operation(operation)

    def _make_request(
        self, operation, parameters=None, request_body=None, mime_type="application/json"
    ):
        """
        Make a request to an implementation of operation in the given
        OpenAPI specification.

        See ``check_operation_conformance`` for information about
        ``send_request``.

        :param operation: openapi_core Operation object.
        :param parameters: openapi_core Parameters object.
        :param request_body: data to send in the request body.
        :param mime_type: the mime type of the request body.

        :return: tuple of (BaseOpenAPIRequest, BaseOpenAPIResponse)
        """
        path = self.specification.default_url + operation.path_name
        slashes = ("/" if x("/") else "" for x in (path.startswith, path.endswith))
        path = path.strip("/").join(slashes)

        if parameters:
            view_args = {}
            args = {}
            for parameter, value in parameters:
                if parameter.location == ParameterLocation.PATH:
                    view_args[parameter.name] = value
                elif parameter.location == ParameterLocation.QUERY:
                    args[parameter.name] = value
        else:
            args = {}
            view_args = {}

        if request_body is not None:
            data = self.mime_type_decoders[mime_type](request_body)
        else:
            data = b""

        request = MockRequest(
            f"http://host.com/",
            operation.http_method,
            path=path,
            args=args,
            view_args=view_args,
            data=data,
            mimetype=mime_type,
        )
        return request, self.send_request(operation, request)
