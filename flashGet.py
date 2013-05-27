#!/usr/bin/env python
# coding:utf-8

import logging
import time
import threading
from Queue import Queue
import re
import traceback
from itertools import izip

from slidingWindow import SlidingWindow
from connectionPool import pools
from config import AUTORANGE_MAXSIZE, \
                PRE_READ_SIZE, \
                THREAD_POOL_SIZE, \
                SOCKET_TIMEOUT_SEC, \
                MAX_RETRY

class TaskQueue(object):
    """
    Flexible thread pool class.  Creates a pool of threads, then
    accepts tasks that will be dispatched to the next available
    thread. Blocks if thread-pool-size is reached.
    """

    def __new__(cls, *args, **kwargs):
        """A pythonic singleton"""
        if '_inst' not in vars(cls):
            cls._inst = super(TaskQueue, cls).__new__(cls, *args, **kwargs)
        return cls._inst

    def __init__(self, size=5):
        self.queue = Queue(size)
        for i in range(size):
            threading.Thread(target=self.work).start()

    def add_task(self, callable_task):
        self.queue.put(callable_task)
    
    def work(self):
        while True:
            try:
                self.queue.get()()
                self.queue.task_done()
            except Exception as e:
                logging.exception(e)
    
    def wait_all_done(self):
        self.queue.join()

task_queue = TaskQueue(THREAD_POOL_SIZE)

class AtomicInt(object):
    """like AtomicInteger in Java"""
    def __init__(self, init_value=0):
        self.value = init_value
        self.update_mutex = threading.Lock()

    def __iadd__(self, delta):
        with self.update_mutex:
            self.value += delta
            return self

    def __float__(self):
        with self.update_mutex:
            return float(self.value)


class FlashGet(object):
    http_vsn_str = {11:'HTTP/1.1', 10:'HTTP/1.0', 9:'HTTP/0.9'}
    
    def __init__(self, request):
        self.request = request
        self.response = pools[request.url].urlopen(request)

    def __getattr__(self, name):
        return getattr(self.response, name)

    def content_length(self):
        return int(self.getheader('Content-Length', 0))

    def support_ac_range(self):
        """return true if the server-side support Accept-Range header"""
        # http 1.0 support too.
        return self.status==200 and \
                self.getheader('accept-range') != 'none'

    def need_for_speed(self):
        if self.content_length()>AUTORANGE_MAXSIZE and self.support_ac_range():
            return True
        return False

    def fetch_from(self):
        if self.status == 206:
            print 'he'*20 #TODO: test here
            return PRE_READ_SIZE+int(re.search(r'bytes (\d+)-\d+/\d+', self.getheader('Content-Range')).group(1))
        return PRE_READ_SIZE

    def download(self):
        req = self.request
        resp = self.response
        yield '%s %s %s\r\n%s\r\n%s' % (self.__class__.http_vsn_str[resp.version], resp.status, resp.reason,
            ''.join('%s: %s\r\n' % (k, v) for k, v in resp.getheaders() if k!='transfer-encoding'),
            resp.read(PRE_READ_SIZE))
        if self.need_for_speed():
            for data in self.spawn():
                yield data
        else:
            logging.info('%s "%s" %d %s', 
                req.method, req.url, self.status, self.content_length() or '-')
            yield resp.read()

    def spawn(self):
        # self.conn.close()  # ensure closed
        start = self.fetch_from()
        tot_size = self.content_length()
        sliding_window = SlidingWindow(start, tot_size, THREAD_POOL_SIZE)
        # int passed by value not reference, 
        # in this model I need threads to share the same var, thus created in the public place
        finished = AtomicInt(PRE_READ_SIZE)

        def async_spawn():
            for wnd in sliding_window.available_window():
                # self.headers.copy(), multiple threads will modify headers so we cannot share it
                rf = RangeFetch(self.request.copy(), wnd, finished, tot_size)
                task_queue.add_task(rf.fetch)
                time.sleep(3)

        threading.Thread(target=async_spawn).start()

        for data in sliding_window.full_window():
            yield data

    def formatKMGT(self, num):
        if num>=1<<40:
            return '%.2fT' % (float(num)/(1<<40))
        elif num>=1<<30:
            return '%.2fG' % (float(num)/(1<<30))
        elif num>=1<<20:
            return '%.2fM' % (float(num)/(1<<20))
        elif num>=1<<10:
            return '%.2fK' % (float(num)/(1<<10))
        return str(num)
        

class RangeFetch(FlashGet):

    def __init__(self, req, window, finished, tot_size, max_retry=MAX_RETRY):
        self.req = req
        self.window = window
        self.finished = finished
        self.tot_size = tot_size
        self.max_retry = max_retry

    def fetch(self):
        from_ = self.window.first
        to = self.window.last
        self.req.add_header('Range', 'bytes=%d-%d' % (from_, to))
        self.req.add_header('Connection', 'keep-alive')

        for i in xrange(self.max_retry):
            if self.req.is_closed(): return
            try:
                time_start = time.time()

                resp = pools[self.req.url].urlopen(self.req)
                assert resp.status == 206, 'actually is %d' % resp.status
                self.response = resp  # set for the __getattr__ call
                self.window.fill(resp.read())
                if resp.getheader('Connection', 'closed').lower()=='keep-alive':
                    resp.release_conn()
                assert self.content_length()==to-from_+1, 'expected %d, received %d' % (self.content_length(), to-from_+1)

                time_elapsed = time.time()-time_start
            except Exception as e:
                if i != self.max_retry-1:
                    logging.exception('The #%d attempt to fetch %d-%d failed, try again.', i+1, from_, to)
                    time.sleep(2)
            else:
                self.finished += self.content_length()
                speed = self.content_length()/time_elapsed
                SlidingWindow.adjust_wnd_size(speed*SOCKET_TIMEOUT_SEC)
                logging.info('Content-Range %s, "%s" at %sB/s, finished %.2f%%', self.getheader('Content-Range')[6:], self.req.url, 
                    self.formatKMGT(speed), 100*float(self.finished)/self.tot_size)
                return
        else:
            logging.exception('>>>>>>>>>>>>>>> Range Fetch failed(%r) %d-%d', self.req.url, from_, to)

