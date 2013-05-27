#!/usr/bin/env python
# coding:utf-8
from request import Request
from threading import Event

e = Event()
r = Request('Get', 'www.google.com', close_event=e)
print r.path
print str(r)
r1 = r.copy()
print r.close_event is r1.close_event
print r.headers is r1.headers
