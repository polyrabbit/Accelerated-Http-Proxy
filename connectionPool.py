#!/usr/bin/env python
# coding:utf-8
import collections
import httplib
import threading
import socket
import logging
from urlparse import urlparse
try:
    from select import poll, POLLIN
except ImportError:  # `poll` doesn't exist on OSX and other platforms
    poll = False
    try:
        from select import select
    except ImportError:  # `select` doesn't exist on AppEngine.
        select = False

import config

# http://stackoverflow.com/questions/2912231/is-there-a-clever-way-to-pass-the-key-to-defaultdicts-default-factory
class keydefaultdict(collections.defaultdict):
    update_mutex = threading.Lock()

    def __getitem__(self, key):
        # urlparse have cache inside
        scheme, netloc, path, params, query, frag = urlparse(key)
        return super(keydefaultdict, self).__getitem__(netloc)

    def __missing__(self, key):
        with keydefaultdict.update_mutex:
            if self.default_factory is None:
                raise KeyError(key)
            else:
                ret = self[key] = self.default_factory(key)
                return ret

# from urllib3
_Null = object()
class RecentUsedDict(collections.MutableMapping):
    """
    Provides a thread-safe dict-like container which maintains up to
    ``maxsize`` keys while throwing away the least-recently-used keys beyond
    ``maxsize``.

    :param maxsize:
        Maximum number of recent elements to retain.

    :param dispose_func:
        Every time an item is evicted from the container,
        ``dispose_func(value)`` is called.  Callback which will get called
    """
    def __init__(self, maxsize=10, dispose_func=None):
        self._maxsize = maxsize
        self.dispose_func = dispose_func

        self._container = collections.OrderedDict()
        self._lock = threading.Lock()

    def __getitem__(self, key):
        # Re-insert the item, moving it to the end of the eviction line.
        with self._lock:
            item = self._container.pop(key)
            self._container[key] = item
            return item

    def __setitem__(self, key, value):
        evicted_value = _Null
        with self._lock:
            # Possibly evict the existing value of 'key'
            evicted_value = self._container.get(key, _Null)
            self._container[key] = value

            # If we didn't evict an existing value, we might have to evict the
            # least recently used item from the beginning of the container.
            if len(self._container) > self._maxsize:
                _key, evicted_value = self._container.popitem(last=False)

        if self.dispose_func and evicted_value is not _Null:
            self.dispose_func(evicted_value)

    def __delitem__(self, key):
        with self._lock:
            value = self._container.pop(key)

        if self.dispose_func:
            self.dispose_func(value)

    def __len__(self):
        with self._lock:
            return len(self._container)

    def __iter__(self):
        raise NotImplementedError('Iteration over this class is unlikely to be threadsafe.')

    def __contains__(self, key):  # for in
        with self._lock:
            return key in self._container

    def clear(self):
        with self._lock:
            # Copy pointers to all values, then wipe the mapping
            # under Python 2, this copies the list of values twice :-|
            values = list(self._container.values())
            self._container.clear()

        if self.dispose_func:
            for value in values:
                self.dispose_func(value)

    def keys(self):
        with self._lock:
            return self._container.keys()


class ConnectionPool(object):
    lock = threading.Lock()

    def __init__(self, host):
        # If there is a port, it should be appended after the 
        # host, let the underlying httplib worry about the port.
        self.host = host
        self.pool = collections.deque()

    def _is_connection_dropped(self, conn):  # Platform-specific
        """
        Returns True if the connection is dropped and should be closed.

        :param conn:
            :class:`httplib.HTTPConnection` object.
        """
        sock = getattr(conn, 'sock', False)
        if not sock: # Platform-specific: AppEngine
            return False

        if not poll:
            if not select: # Platform-specific: AppEngine
                return False

            try:
                return select([sock], [], [], 0.0)[0]
            except socket.error:
                return True

        # This version is better on platforms that support it.
        p = poll()
        p.register(sock, POLLIN)
        for (fno, ev) in p.poll(0.0):
            if fno == sock.fileno():
                # Either data is buffered (bad), or the connection is dropped.
                return True

    def _new_conn(self):
        conn = httplib.HTTPConnection(self.host, timeout=config.SOCKET_TIMEOUT_SEC)
        # conn = socket.create_connection((self.host))
        # cautious: may release more than once
        # conn.release = lambda : self.pool.append(conn)
        return conn

    def _get_conn(self):
        with self.lock:
            conn = None
            try:
                conn = self.pool.pop()  # popright
            except IndexError:  # self.pool is empty
                pass
            # If this is a persistent connection, check if it got disconnected
            if conn and self._is_connection_dropped(conn):
                conn.close()
                conn = None

            return conn or self._new_conn()

    def _put_conn(self, conn):
        with self.lock:
            self.pool.append(conn)

    def urlopen(self, request):
        conn = self._get_conn()
        conn.request(request.method, request.path, request.body, request.headers)
        #  fuck me, httplib
        # conn.send(str(request))  # HTTPConnection has a hidden method called send.
        # conn._HTTPConnection__state = httplib._CS_REQ_SENT # I need to write my own httplib
        r = conn.getresponse()
        r.release_conn = lambda: self._put_conn(conn)
        return r

    def clear(self):
        self.pool.clear()

class PoolManager(object):
    lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """A pythonic singleton"""
        if '_inst' not in vars(cls):
            cls._inst = super(PoolManager, cls).__new__(cls, *args, **kwargs)
        return cls._inst

    def __init__(self):
        self._pools = RecentUsedDict(dispose_func=lambda p: p.close())

    def _new_pool(self, host):
        return ConnectionPool(host)

    def clear(self):
        self._pools.clear()

    def __getitem__(self, host):
        """
        Get a :class:`ConnectionPool` based on the host
        """
        with self.lock:
            if host in self._pools:
                return self._pools[host]
            # Make a fresh ConnectionPool of the desired type
            pool = self._new_pool(host)
            self._pools[host] = pool
            return pool

pools = PoolManager()
# deprecated
pools = keydefaultdict(ConnectionPool)

if __name__ == '__main__':
    url = 'http://www.google.com'
    pool = pools[url]
    assert pool.host=='www.google.com'

    pool1 = pools[url]
    assert pool is pool1

    conn = pool.pick()
    conn.release()
    print pool1.connections
    pool.pick()
    c2 = pool.pick()
    c2.release()
    print pool1.pick() is c2
    print pools[url+'?fd=9#fdsa'] is pool
