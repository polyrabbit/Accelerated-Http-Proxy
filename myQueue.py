#!/usr/bin/env python
# coding:utf-8

import time
import threading
import Queue

class MyQueue(Queue.Queue):

    def __init__(self, maxsize=0):
        # Queue.Queue is not derived from object
        Queue.Queue.__init__(self, maxsize)
        not_empty_wake_all = Queue._threading.Condition(self.mutex)
        # notify_all will call self.notify(len(self.__waiters))
        # not_empty_wake_all.notify = not_empty_wake_all.notify_all
        _notify = not_empty_wake_all.notify
        def _notify_all(n=None):
            if n is None:
                return not_empty_wake_all.notify_all()
            return _notify(n)
        not_empty_wake_all.notify = _notify_all
        self.not_empty = not_empty_wake_all

    def wait_used(self):
        """wait until this queue has at least one item"""
        with self.not_empty:
            self.not_empty.wait()

def test_wait(que):
    print '-'*40
    que.wait_used()
    print '*'*40

def test_get(que):
    print '-'*40
    que.get()
    print '*'*40

def test():
    que = MyQueue()
    threading.Thread(target=test_wait, args=(que,)).start()
    threading.Thread(target=test_get, args=(que,)).start()
    time.sleep(3)
    que.put(3)


if __name__ == '__main__':
    test()