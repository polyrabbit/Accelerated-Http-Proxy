# coding:utf-8
from urlparse import urlparse
from copy import copy
from threading import Event

__all__ = ['Request']

class Request(object):
    '''
    自从有了Request，妈妈再也不用担心我要传递的参数太多了。
    '''
    def __init__(self, method, url, version='HTTP/1.1', headers={}, body=None, close_event=Event()):
        self.method = method
        self.url = url
        self.version = version
        self.headers = headers
        self.body = body
        # a very dirty way to inform workers that the source has been closed,
        # need a better idea.
        self.close_event = close_event
        self.parse_url()

    def parse_url(self):
        scheme, host, path, params, query, frag = urlparse(self.url, scheme='grass-mud-horse')
        if scheme == 'grass-mud-horse':
            scheme, host, path, params, query, frag = urlparse(
                    'http://'+self.url, scheme='grass-mud-horse')
        self.scheme = scheme
        self.host = host
        if query:
            path += '?'+query
        self.path = path or '/'

    def add_header(self, key, value):
        self.headers[key] = value

    def close(self):
        self.close_event.set()

    def is_closed(self):
        return self.close_event.is_set()

    def header_str(self):
        request_line = '%s %s %s' % (self.method, self.path, self.version)
        hdr_lines = []
        for k, v in self.headers.items():
            hdr_lines.append('%s: %s' % (k, v))
        return '%s\r\n%s\r\n\r\n' % (request_line, '\r\n'.join(hdr_lines))

    def copy(self):
        """
        Returns a shallow copy of self, in which most of the attrs refer to the old one,
        while headers are not, because each thread owns a different header.
        """
        shallow_copy = copy(self)
        shallow_copy.headers = self.headers.copy()
        return shallow_copy

    def __str__(self):
        return self.header_str()+(self.body or '')
