json_home_client
================

Client class for calling http+json APIs in Python. Requires Python 3.6+.

Suports json home pages per:
https://tools.ietf.org/html/draft-nottingham-json-home-06


Installation
------------
Standard python package installation:

       pip install json-home-client


Usage
-----
Import the json_home_client package and instantiate a client.

       from json_home_client import Client

       api = Client('http://api.example.com')

Call APIs:

       result = api.call('foo', var1=arg1, var2=arg2)
       print result.data


Client class
---------------
**class json_home_client.Client(base_url: str, version: str = None, username: str = None, password: str = None, user_agent: str = None)**

The Client constructor takes the base URL for the api, an optional request version identifier, username and password.

**Client.base_url: str**

The base URL set in the constructor, read-only.

**Client.default_version: Optional[str]**

The default version information for accept headers.

**Client.default_accept: MimeType**

The default accept types for API calls.

**Client.username: Optional[str]**

Username to send in HTTP authentication header.

**Client.password: Optional[str]**

Password to send in HTTP authentication header.

**Client.user_agent: str**

The User-Agent string to send in requests.

**Client.resource_names: Sequence[str]**

A list of available API resource names.

**Client.resource(name: str) -> Resource**

Get a named Resource.

**Client.add_resource(name: str, url: str) -> None**

Add a URL resource.

**Client.set_version(name: str, version: str = None) -> None**

Set the request version identifier for a specific resource. If not set, the default version identifer will be used.

**Client.set_accept(name: str, content_type: Union[MimeType, Sequence[MimeType]]) -> None**

Set the requested Content-Type(s) for a specific resource. If not set, 'application/json' will be used.

**Client.get(name: str, **kwargs) -> Optional[Response]**

Perform an HTTP GET on the named resource. Any named arguments supplied may be used in computing the actual URL to call. Returns a Response or None if the resource name is not known.

**Client.post(name: str, payload: bytes, content_type: MimeType = None, **kwargs) -> Optional[Response]**

Perform an HTTP POST on the named resource. Any named arguments supplied may be used in computing the actual URL to call. Returns a Response or None if the resource name is not known.

**Client.post_form(name: str, payload: Mapping[str, Any] = None, **kwargs) -> Optional[Response]**

Perform an HTTP POST on the named resource. The payload, if present, will be URL form encoded. Any named arguments supplied may be used in computing the actual URL to call. Returns a Response or None if the resource name is not known.

**Client.post_json(name: str, payload: Any = None, **kwargs) -> Optional[Response]**

Perform an HTTP POST on the named resource. The payload, if present, will be converted to JSON. Any named arguments supplied may be used in computing the actual URL to call. Returns a Response or None if the resource name is not known.

**Client.put(name: str, payload = None, content_type: MimeType = None, **kwargs) -> Optional[Response]**

Perform an HTTP PUT on the named resource. The payload, if present, will be sent to the server using the provided Content-Type. The payload must be pre-encoded and will not be processed by the Client. Any named arguments supplied may be used in computing the actual URL to call. Returns a Response or None if the resource name is not known.

**Client.patch(name: str, patch: Mapping[str, Any] = None, content_type: MimeType = MimeType.JSON_PATCH, **kwargs) -> Optional[Response]**

Perform an HTTP PATCH on the named resource. The patch, if present, will be encoded in JSON and sent to the server as a 'application/json-patch'. Any named arguments supplied may be used in computing the actual URL to call. Returns a Response or None if the resource name is not known.

**Client.delete(name: str, **kwargs) -> Optional[Response]**

Perform an HTTP DELETE on the named resource. Any named arguments supplied may be used in computing the actual URL to call. Returns a Response or None if the resource name is not known.


Response class
-----------------
**Response.status_code: int**

The HTTP status code of the response.

**Response.headers: Mapping[str, Any]**

A dict of HTTP response headers.

**Response.conten_type: MimeType**

The Content-Type of the response.

**Response.encoding: str**

The encoding of the response.

**Response.data: Any**

The body of the response. If the contentType is json, the data will be decoded into native objects.


Resource class
-----------------
Describes the properties of an available API resource.

**Resource.template**

The URITemplate used when calling the resource.

**Resource.variables**

A dict of variables that may be passed to the resource. Keys are variable names, values are the URL identifier of the variable, if available (see https://tools.ietf.org/html/draft-nottingham-json-home-06#section-4.1 ).

**Resource.hints**

An Hints object describing any hints for the resource (see https://tools.ietf.org/html/draft-nottingham-json-home-06#section-5 ).


Hints class
--------------
**Hints.http_methods: Sequence[str]**

A list of HTTP methods the resource may be called with.

**Hints.formats: Mapping[str, Sequence[MimeType]]**

A dict of formats available for each HTTP method. Keys are HTTP methods, values are a list of Content-Types available.

**Hints.ranges: Optional[Sequence[str]]**

A list of range specifiers.

**Hints.preferences: Optional[Sequence[str]]**

A list of preferences supported by the resource.

**Hints.preconditions: Optional[Sequence[str]]**

A list of preconditions required by the resource.

**Hints.auth: Optional[Sequence[Mapping[str, str]]]**

A list of authorization schemes accepted by the resource.

**Hints.docs: Optional[str]**

A URL for documentation for the resource.

**Hints.status: Optional[str]**

The status of the resource.


MimeType class
--------------
**MimeType(mime_type: str = None, type: str = None, structure: str = None, subtype: str = None)**

Constructor, accepts a mime_type, which will be parsed, or individual components.

**MimeType.type: str**

The primary type, e.g. "application/json" -> "application"

**MimeType.structure: Optional[str]**

The structure, e.g. "application/json" -> "json", "application/vnd.app.v1+json" -> "json"

**MimeType.subtype: Optional[str]**

The subtype, e.g. "application/vnd.app.v1+json" -> "vnd.app.v1"


Notes
-----
Resource names may be absolute URLs or relative to the base URL of the API.
