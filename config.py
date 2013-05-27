import logging
from urlparse import urlparse

SOCKET_TIMEOUT_SEC = 30
BIND_IP = '0.0.0.0'
BIND_PORT = 27015

debuglevel = 1  # for flashGet

logging._srcfile = None
logging.logProcesses = 0
logging.basicConfig(level=logging.INFO, format='%(levelname)s - - %(asctime)s - %(message)s', datefmt='%H:%M:%S')

urlparse.MAX_CACHE_SIZE = 100

AUTORANGE_MAXSIZE = 512*1024
PRE_READ_SIZE = 1024
MAX_RETRY = 3
THREAD_POOL_SIZE = 5
SOCKET_TIMEOUT_SEC = 30
