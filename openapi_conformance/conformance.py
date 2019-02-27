# std
import json

# 3rd party
from hypothesis import given
from openapi_core.schema.parameters.enums import ParameterLocation
from openapi_core.validation.response.validators import ResponseValidator
from openapi_core.wrappers.mock import MockRequest, MockResponse

# openapi_conformance
from openapi_conformance.extension import (
    create_spec,
    operations,
    raise_verbose_exception,
    record_unmarshal,
    strict_str,
)
from openapi_conformance.strategies import Strategies


class OpenAPIConformance:
    """

    """

    def __init__(self, specification, send_request, format_strategies=None):
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
        """
        self.specification = create_spec(specification)
        self.send_request = send_request
        self.st = Strategies(format_strategies)

    @property
    def operations(self):
        """
        :return: All the operations in the specification.
        """
        return operations(self.specification)

    def check_response_conformance(self, request, response):
        """
        Check that a given response conforms to the specified valid
        responses.

        :param request: openapi_core BaseOpenAPIRequest object
        :param response: openapi_core BaseOpenAPIResponse object
        """
        # TODO: Custom formatting
        with record_unmarshal() as log:
            with strict_str():
                validator = ResponseValidator(self.specification)
                result = validator.validate(request, response)
                try:
                    result.raise_for_errors()
                except Exception as e:
                    raise_verbose_exception(e, log)

    def check_operation_conformance(self, operation):
        """
        Check that the implementation of a given operation conforms to
        the specification. If the implementation doesn't conform to the
        specification then an Exception is raised.

        :param operation: openapi_core Operation object
        """

        def _request_and_check(parameters=None, body=None):
            responses = list(self._make_request(operation, parameters, body))
            if responses:
                for request, response in self._make_request(operation, parameters, body):
                    self.check_response_conformance(request, response)
            else:
                pass  # check we actually expected an empty response

        # We cannot use star args with the given decorator, which means
        # we need to define three seperate functions depending on the
        # presence of roperation.request_body and operation.parameters

        given_args = []
        if operation.parameters:
            strategy = self.st.parameter_lists(operation.parameters)
            given_args.append(strategy)

        if operation.request_body is not None:
            schema = operation.request_body.content["application/json"].schema
            strategy = self.st.schema_values(schema)
            given_args.append(strategy)

        if operation.request_body and operation.parameters:

            @given(*given_args)
            def _hypothesized_request_and_check(p, r):
                _request_and_check(p, r)

        elif operation.parameters:

            @given(*given_args)
            def _hypothesized_request_and_check(p):
                _request_and_check(p)

        else:

            @given(*given_args)
            def _hypothesized_request_and_check(r):
                _request_and_check(None, r)

        is_hypothesized = operation.parameters or operation.request_body
        _hypothesized_request_and_check() if is_hypothesized else _request_and_check()

    def check_specification_conformance(self):
        """
        Check that an implementation conforms to the given
        specification.

        If the implementation doesn't conform to the specification then
        an Exception is raised.

        :param specification: openapi_core` Spec object
        :param send_request: Callable to invoke the implementation.
        """
        for operation in self.operations:
            self.check_operation_conformance(operation)

    def _make_request(self, operation, parameters=None, request_body=None):
        """
        Make a request to an implementation of operation in the given
        OpenAPI specification.

        See ``check_operation_conformance`` for information about
        ``send_request``.

        :param operation: openapi_core Operation object.
        :param parameters: openapi_core Parameters object.
        :param request_body: data to send in the request body

        :return: tuple of (BaseOpenAPIRequest, BaseOpenAPIResponse)
        """
        path = self.specification.default_url + operation.path_name
        slashes = ("/" if x("/") else "" for x in (path.startswith, path.endswith))
        path = path.strip("/").join(slashes)

        # TODO: Other parameter locations
        if parameters:
            view_args = {}
            args = {}
            for parameter, value in parameters:
                # TODO: Formatting of parameter values
                if parameter.location == ParameterLocation.PATH:
                    view_args[parameter.name] = value
                elif parameter.location == ParameterLocation.QUERY:
                    args[parameter.name] = value
        else:
            args = {}
            view_args = {}

        # TODO: Use correct mime type
        data = json.dumps(request_body).encode() if request_body else None

        request = MockRequest(
            f"http://host.com/",  # TODO: What to use for URL here?
            operation.http_method,
            path=path,
            args=args,
            view_args=view_args,
            data=data,
        )

        for status_code, response in operation.responses.items():
            if response.content:
                for mimetype, schema in response.content.items():
                    yield request, self.send_request(
                        request, operation, status_code, mimetype, schema
                    )
            else:
                yield request, MockResponse(b"", status_code)
