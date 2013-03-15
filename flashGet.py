#!/usr/bin/env python
# coding:utf-8

import httplib
import logging
import time
import urlparse
import threading
from Queue import Queue
import re
import traceback
from itertools import izip

AUTORANGE_MAXSIZE = 1024*1024
minsize = 256*1024
#NOTE: youku will response with 403 if block_size is too small
AUTORANGE_MAXSIZE = 512*1024
PRE_READ_SIZE = 1024
MAX_RETRY = 2
THREAD_POOL_SIZE = 5
SOCKET_TIMEOUT_SEC = 30
debuglevel = 0

class TaskQueue(object):
    
    def __init__(self, size):
        self.queue = Queue(size)
        for i in range(size):
            threading.Thread(target=self.work).start()

    def add_task(self, callable):
        self.queue.put(callable)
    
    def work(self):
        while True:
            try:
                self.queue.get()()
            except Exception as e:
                logging.exception(e)

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
        

def create_connection(method, url, payload, headers):
    # urlparse have cache inside
    scheme, netloc, path, params, query, frag = urlparse.urlparse(url)
    if query:
        path += '?' + query
    # it will just stop there if without timeout
    conn = httplib.HTTPConnection(netloc, timeout=SOCKET_TIMEOUT_SEC)
    conn.set_debuglevel(debuglevel)
    # request will send all the data out, time-consumer
    conn.request(method=method, url=path, body=payload, headers=headers)
    return conn

class FlashGet(object):
    http_vsn_str = {11:'HTTP/1.1', 10:'HTTP/1.0', 9:'HTTP/0.9'}
    
    def __init__(self, method, url, payload, headers, stopped):
        self.method = method
        self.payload = payload
        self.headers = headers
        #TODO: memorize it
        # self.url = urlparse.urlparse(url)
        self.url = url
        self.stopped = stopped
        self.conn = create_connection(method, url, payload, headers)

        self.response = self.conn.getresponse()

    def __getattr__(self, name):
        return getattr(self.response, name)

    def content_length(self):
        return int(self.getheader('Content-Length', 0))

    def support_ac_range(self):
        """return true if the server-side support Accept-Range header"""
        # http 1.0 support too.
        return self.getheader('accept-range') != 'none'

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
        resp = self.response
        yield '%s %s %s\r\n%s\r\n%s' % (self.http_vsn_str[self.version], self.status, self.reason,
            ''.join('%s: %s\r\n' % (k, v) for k, v in self.getheaders() if k!='transfer-encoding'),
            self.read(PRE_READ_SIZE))
        if self.need_for_speed():
            print '-'*40, 'header finished'
            for data in self.spawn():
                yield data
        else:
            logging.info('%s "%s" %d %s', 
                self.method, self.url, self.status, self.content_length() or '-')
            yield self.read()

    def spawn(self):
        self.conn.close()  # ensure closed
        start = self.fetch_from()
        tot_size = self.content_length()
        range_starts = xrange(start, tot_size, AUTORANGE_MAXSIZE)
        buckets = [Queue() for i in range_starts]
        # int passed by value not reference, 
        # in this model I need threads to share the same var, thus created in the public place
        finished = AtomicInt(0)
        

        def async_spawn():
            is_first = False  # I use pre-read to avoid you 
            for buck, st in izip(buckets, range_starts):
                ed = min(st+AUTORANGE_MAXSIZE-1, tot_size-1)
                # self.headers.copy(), multiple threads will modify headers so we cannot share it
                rf = RangeFetch(self.method, self.url, self.payload, self.headers.copy(), st, ed, buck, finished, tot_size, self.stopped)
                task_queue.add_task(rf.fetch)
                #TODO: block to download the first part
                if is_first:
                    buck.wait_used()
                    is_first = False

        threading.Thread(target=async_spawn).start()

        for buck in buckets:
            data =  buck.get()
            if data is StopIteration:
                return
            yield data
        

class RangeFetch(FlashGet):

    def __init__(self, method, url, payload, headers, from_, to, bucket, finished, tot_size, stopped, max_retry=MAX_RETRY):
        self.method = method
        self.url = url
        self.payload = payload
        self.headers = headers
        self.from_ = from_
        self.to = to
        self.bucket = bucket
        self.finished = finished
        self.tot_size = tot_size
        self.stopped = stopped
        self.max_retry = max_retry

    def fetch(self):
        self.headers['Range'] = 'bytes=%d-%d' % (self.from_, self.to)
        self.headers['Connection'] = 'close'

        for i in xrange(self.max_retry):
            if self.stopped.is_set(): return
            try:
                time_start = time.time()

                self.conn = create_connection(self.method, self.url, self.payload, self.headers)
                self.response = self.conn.getresponse()
                resp = self.response
                assert resp.status == 206, 'actually is %d' % resp.status
                self.bucket.put(resp.read())
                self.conn.close()
                assert self.content_length()==self.to-self.from_+1, 'expected %d, received %d' % (self.content_length(), self.to-self.from_+1)

                time_elapsed = time.time()-time_start
            except Exception as e:
                if i != self.max_retry-1:
                    logging.exception('The #%d attempt to fetch %d-%d failed, try again.', i+1, self.from_, self.to)
                    time.sleep(2)
            else:
                self.finished += self.content_length()
                logging.info('Content-Range %s, "%s" at %.2fKB/s, finished %.2f%%', self.getheader('Content-Range')[6:], self.url, 
                    self.content_length()/time_elapsed/1024, 100*float(self.finished)/self.tot_size)
                return
        else:
            logging.exception('>>>>>>>>>>>>>>> Range Fetch failed(%r) %d-%d', self.url, self.from_, self.to)