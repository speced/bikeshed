"""Client for REST APIs that provide a JSON Home Page per http://tools.ietf.org/html/draft-nottingham-json-home-06."""

from .client import Client, Hints, MimeType, Resource, Response

__all__ = ['Client', 'Resource', 'Hints', 'Response', 'MimeType']
