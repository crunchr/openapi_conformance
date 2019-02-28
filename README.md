# OpenAPI conformance

A tool for validating an [OpenAPI 3.0](https://swagger.io/docs/specification/about/) specification 
against an implementation.

The main idea is to generate multiple requests (with parameters and request body being generated using [hypothesis](https://hypothesis.works) according to the schemas defined in the specification) for the operations, passing these to the supplied``send_request`` function which is responsible for sending the request and returning the response, which in turn is validated against the specification using [openapi_core](https://github.com/p1c2u/openapi-core). When an unexpected response occurs an exception is raised.

## Motivation

This tool is especially useful when you have an OpenAPI specification and an implementation of that spec and you want to check that the implementation actually conforms to the specification.

## Installation

Use a package manager (e.g. [poetry](https://poetry.eustace.io/docs/), [pipenv](https://pipenv.readthedocs.io/en/latest/) or [pip](https://pip.pypa.io/en/stable/)) e.g.
```bash
$ poetry add openapi_conformance
```

## Usage

The main thing that is required in order to use is to supply a ``send_request`` function which translates a request object to an actual request to the implementation being tested. For example one might invoke an actualy http request using [requests](http://docs.python-requests.org/en/master/), or as in the following example use the [django](https://www.djangoproject.com/) test client to send requests as part of your django tests.

```python
from openapi_core.wrappers.mock import MockResponse
from django.test import Client, TestCase
from openapi_conformance import OpenAPIConformance


class OpenAPIConformanceTestCase(TestCase):

    def test_conformance(self):

        client = Client()
        client.login(**user_credentials)
        
        def send_request(operation, request):
            path = request.path.format(**request.parameters["path"])
            response = getattr(client, request.method)(path)
            return MockResponse(response.content, response.status_code)
        
        openapi_conformance = OpenAPIConformance("petstore.yaml", send_request)
        openapi_conformance.check_specification_conformance()
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

The steps for installing a development environment can be found in ``tools/bootstrap`` you can either run this script, or if you prefer perform the steps manually.

It is also advisable to run ``tools/hooks/install`` to add the pre-push hook to ensure remote changes are always linted and formatted correctly. Formatting can be fixed with the ``tools/format`` script.
