#!/usr/bin/env python
# coding:utf-8

import BaseHTTPServer
import SocketServer
import socket
import threading
from request import Request

import config
import flashGet

class ProxyServer(SocketServer.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

class ProxyRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler, object):
    # Set this to HTTP/1.1 to enable automatic keepalive
    protocol_version = 'HTTP/1.1'
    
    def parse_request(self):
        if not super(ProxyRequestHandler, self).parse_request():
            return False

        pconntype = self.headers.get('Proxy-Connection', '')
        if 'close' in pconntype.lower():  # some say closed
            self.close_connection = 1
        elif (pconntype.lower() == 'keep-alive' and
              self.protocol_version >= 'HTTP/1.1'):
            self.close_connection = 0
        return True

    def handle_one_request(self):
        self.raw_requestline = self.rfile.readline()
        if not self.raw_requestline:
            self.close_connection = 1
            return
        if not self.parse_request():
            # An error code has been sent, just exit
            return

        # self.headers = BaseHTTPRequestHandler.headers = instance of mimetools.Message
        req = Request(
                method = self.command,
                url = self.path,
                version = self.request_version,
                headers = self.headers.dict,
                body = self.body(),
                close_event = self.stopped,
        )

        if req.scheme != 'http':
            self.send_error(501, '%s is not supported, only http works.' % req.scheme)
            return

        fg = flashGet.FlashGet(req)
        for data in fg.download():
            self.wfile.write(data)

    def handle(self):
        """Handle multiple requests if necessary."""
        self.close_connection = 1
        self.stopped = threading.Event() #TODO: need refine

        try:
            self.handle_one_request()
            # while not self.close_connection:
            #    self.handle_one_request()

        except socket.error as e:
            self.stopped.set()
            self.send_error(500, str(e))
            return   

    def body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(content_length) if content_length else None

    def send_error(self, code, message):
        #TODO: use logging for thread-safe
        super(ProxyRequestHandler, self).send_error(code, message)


def main():
    import sys

    if sys.argv[1:]:
        port = int(sys.argv[1])
    else:
        port = config.BIND_PORT
        
    server_address = (config.BIND_IP, port)
    httpd = ProxyServer(server_address, ProxyRequestHandler)

    sa = httpd.server_address
    print "Serving proxy on", sa[0], "port", sa[1], "..."
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return

if __name__ == '__main__':
    main()
