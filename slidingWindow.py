#!/usr/bin/env python
# coding:utf-8

import httplib
import logging
import time
import urlparse
import threading
import Queue
import re
import traceback
import itertools

SOCKET_TIMEOUT_SEC = 30

class Window(object):
	def __init__(self, first, last, bucket):
		self.first = first
		self.last = last
		self.bucket = bucket

	def fill(self, data):
		self.bucket.put(data)

class SlidingWindow(object):
	#NOTE: youku will response with 403 if wnd_size is too small
	MIN_SIZE = 256*1024
	MAX_SIZE = 2*1024*1024
	alpha = 0.6  # smoothing factor
	assert MIN_SIZE<MAX_SIZE
	wnd_size = SOCKET_TIMEOUT_SEC*10*1024
	update_mutex = threading.Lock()

	def __init__(self, first, tot_size, size=5):
		self.first = first
		self.last = tot_size-1
		rcv_wnd = [Queue.Queue() for _ in xrange(size)]
		self.sema_wnd_to_submit = threading.Semaphore(0)		
		self.sema_wnd_available = threading.Semaphore(size)		
		self.last_wnd_accepted = itertools.cycle(rcv_wnd)
		self.last_wnd_received = itertools.cycle(rcv_wnd)

	# http://www.orczhou.com/index.php/2011/10/tcpip-protocol-start-rto/
	@classmethod
	def adjust_wnd_size(cls, last_size):
		with cls.update_mutex:
			smoothed_size = int(cls.wnd_size*(1-cls.alpha)+last_size*cls.alpha)
			cls.wnd_size = min(cls.MAX_SIZE, max(cls.MIN_SIZE, smoothed_size))

	def submit_window(self):
		while True:
			self.sema_wnd_available.release()
			self.sema_wnd_to_submit.acquire()
			data = self.last_wnd_accepted.next().get()
			if data is StopIteration:
				return
			yield data

	def available_window(self):
		st = self.first
		while st<self.last:
			self.sema_wnd_available.acquire()
			self.sema_wnd_to_submit.release()
			ed = min(st+self.__class__.wnd_size-1, self.last)  # unsynced
			if self.last-ed < self.__class__.MIN_SIZE:
				# bigger size is OK. if this should happen,
				# it must be the last part, no one will compete.
				ed = self.last
			yield Window(st, ed, self.last_wnd_received.next())
			st = ed+1

		self.sema_wnd_available.acquire()
		self.sema_wnd_to_submit.release()
		self.last_wnd_received.next().put(StopIteration)

def test_blocking_get():
	size = 3
	sw = SlidingWindow(size)
	for i in range(size):
		sw.next_wnd_available()
	sw.next_wnd_available()

def test_blocking_put():
	size = 3
	sw = SlidingWindow(size)
	for i in range(size):
		sw.next_wnd_available()
	for i in range(size):
		sw.next_wnd_to_submit()
	sw.next_wnd_to_submit()

def test_put_get():
	size = 3
	sw = SlidingWindow(size)
	def async_spawn():
		for i in range(size):
			sw.next_wnd_available().put(i)
		buck = sw.next_wnd_available()
		buck.put(StopIteration)

	threading.Thread(target=async_spawn).start()
	
	while True:
		data = sw.next_wnd_to_submit().get()
		print data


if __name__=='__main__':
	# test_blocking_get()
	# test_blocking_put()
	test_put_get()
