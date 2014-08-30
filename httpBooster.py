#!/usr/bin/env python
# coding:utf-8
import BaseHTTPServer
import httplib
import SocketServer
import struct
import socket
import select
import threading
import logging
import urlparse

import flashGet

BIND_IP = '0.0.0.0'
BIND_PORT = 27015  # I love Counter-Strike

# flashGet.debuglevel = 1
logging._srcfile = None
logging.logProcesses = 0
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s - %(message)s', datefmt='%H:%M:%S')

urlparse.MAX_CACHE_SIZE = 100

class ProxyServer(SocketServer.ThreadingTCPServer):
	allow_reuse_address = True
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
		self.stopped = threading.Event() #TODO: need refine
		self.raw_requestline = self.rfile.readline()
		if not self.raw_requestline:
			self.close_connection = 1
			return
		if not self.parse_request():
			# An error code has been sent, just exit
			return

		if self.get_scheme() != 'http':
			self.send_error(501, '%s is not supported, only http works.' % self.get_scheme())
			return

		# self.headers = BaseHTTPRequestHandler.headers = instance of mimetools.Message
		fg = flashGet.FlashGet(
			method=self.command, 
			url=self.path, 
			payload=self.client_request_body(), 
			headers=self.headers.dict,
			stopped = self.stopped
		)
		for data in fg.download():
			self.wfile.write(data)

		self.wfile.flush()  # actually send the response if not already done.  

	def handle(self):
		"""Handle multiple requests if necessary."""
		self.close_connection = 1

		try:
			self.handle_one_request()
			# while not self.close_connection:
			#	 self.handle_one_request()
		except socket.error as e:
			self.stopped.set()
			self.send_error(500, str(e))
			return   

	def client_request_body(self):
		content_length = int(self.headers.get('Content-Length', 0))
		return self.rfile.read(content_length) if content_length else None

	def get_scheme(self):
		url_obj = urlparse.urlparse(self.path, scheme='grass-mud-horse')
		if url_obj.scheme == 'grass-mud-horse':
			self.path = 'http://'+self.path
			return 'http'
		return url_obj.scheme

	def send_error(self, code, message):
		#TODO: use logging for thread-safe
		super(ProxyRequestHandler, self).send_error(code, message)


def main():
	import sys

	if sys.argv[1:]:
		port = int(sys.argv[1])
	else:
		port = BIND_PORT
		
	server_address = (BIND_IP, port)
	httpd = ProxyServer(server_address, ProxyRequestHandler)

	sa = httpd.server_address
	print "Serving proxy on", sa[0], "port", sa[1], "..."
	httpd.serve_forever()

if __name__ == '__main__':
	main()
