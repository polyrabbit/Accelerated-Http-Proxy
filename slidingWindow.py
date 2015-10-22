#!/usr/bin/env python
# coding:utf-8
import Queue
import itertools
import threading

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
    MAX_SIZE = 5*1024*1024
    alpha = 0.6  # smoothing factor
    assert MIN_SIZE<MAX_SIZE
    wnd_size = SOCKET_TIMEOUT_SEC*10*1024
    update_mutex = threading.Lock()

    def __init__(self, first, tot_size, size=5):
        self.first = first
        self.last = tot_size-1
        rcv_wnd = [Queue.Queue(1) for _ in xrange(size)]
        self.wnd_occupied = threading.Semaphore(0)		
        self.wnd_available = threading.Semaphore(size)		
        self.last_wnd_accepted = itertools.cycle(rcv_wnd)
        self.last_wnd_received = itertools.cycle(rcv_wnd)

    # http://www.orczhou.com/index.php/2011/10/tcpip-protocol-start-rto/
    @classmethod
    def adjust_wnd_size(cls, last_size):
        with cls.update_mutex:
                smoothed_size = int(cls.wnd_size*(1-cls.alpha)+last_size*cls.alpha)
                cls.wnd_size = min(cls.MAX_SIZE, max(cls.MIN_SIZE, smoothed_size))

    def get_head(self):
        self.wnd_available.acquire()  # delete one free window
        self.wnd_occupied.release()
        return self.last_wnd_received.next()

    def get_tail_data(self):
        self.wnd_occupied.acquire()  # delete one occupied window
        data = self.last_wnd_accepted.next().get()
        self.wnd_available.release()
        return data

    def full_window(self):
        while True:
            data = self.get_tail_data()
            if data is StopIteration:
                    return
            yield data

    def available_window(self):
        st = self.first
        while st<self.last:
            ed = min(st+SlidingWindow.wnd_size-1, self.last)  # unsynced
            if self.last-ed < SlidingWindow.MIN_SIZE:
                    # bigger size is OK. if this should happen,
                    # it must be the last part, no one will compete.
                    ed = self.last
            yield Window(st, ed, self.get_head())
            st = ed+1

        self.get_head().put(StopIteration)

if __name__=='__main__':
	# test_blocking_get()
	# test_blocking_put()
	test_put_get()
