import logging
import socket
import struct
import json

import Pyro4
from ryu.lib import addrconv
from webob import Response

from ryuo.constants import UINT32_MAX


class UnixTimeStampFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return "{0:.6f}".format(record.created)


def config_logger(logger):
    formatter = UnixTimeStampFormatter(
        '[%(name)s][%(levelname)s][%(asctime)s]: %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False


def mask_ntob(mask, err_msg=None):
    try:
        return (UINT32_MAX << (32 - mask)) & UINT32_MAX
    except ValueError:
        msg = 'illegal netmask'
        if err_msg is not None:
            msg = '%s %s' % (err_msg, msg)
        raise ValueError(msg)


def ip_addr_aton(ip_str, err_msg=None):
    try:
        return addrconv.ipv4.bin_to_text(socket.inet_aton(ip_str))
    except (struct.error, socket.error) as e:
        if err_msg is not None:
            e.message = '%s %s' % (err_msg, e.message)
        raise ValueError(e.message)


def ip_addr_ntoa(ip):
    return socket.inet_ntoa(addrconv.ipv4.text_to_bin(ip))


def ipv4_apply_mask(address, prefix_len, err_msg=None):
    assert isinstance(address, str)
    address_int = ipv4_text_to_int(address)
    return ipv4_int_to_text(address_int & mask_ntob(prefix_len, err_msg))


def ipv4_int_to_text(ip_int):
    assert isinstance(ip_int, (int, long))
    return addrconv.ipv4.bin_to_text(struct.pack('!I', ip_int))


def ipv4_text_to_int(ip_text):
    if ip_text == 0:
        return ip_text
    assert isinstance(ip_text, str)
    return struct.unpack('!I', addrconv.ipv4.text_to_bin(ip_text))[0]


def nw_addr_aton(nw_addr, err_msg=None):
    ip_mask = nw_addr.split('/')
    default_route = ip_addr_aton(ip_mask[0], err_msg=err_msg)
    netmask = 32
    if len(ip_mask) == 2:
        try:
            netmask = int(ip_mask[1])
        except ValueError as e:
            if err_msg is not None:
                e.message = '%s %s' % (err_msg, e.message)
            raise ValueError(e.message)
    if netmask < 0:
        msg = 'illegal netmask'
        if err_msg is not None:
            msg = '%s %s' % (err_msg, msg)
        raise ValueError(msg)
    nw_addr = ipv4_apply_mask(default_route, netmask, err_msg)
    return nw_addr, netmask, default_route


def json_response(obj, status=200):
    return Response(status=status, content_type='application/json',
                    body=json.dumps(obj))


def error_response(status, msg):
    return json_response(msg, status=status)


def int_to_dpid(dpid):
    return hex(dpid)[2:]


def lock_class(methodnames, lockfactory):
    return lambda cls: make_threadsafe(cls, methodnames, lockfactory)


def lock_method(method):
    if getattr(method, '__is_locked', False):
        raise TypeError("Method %r is already locked!" % method)

    def locked_method(self, *arg, **kwarg):
        with self._lock:
            return method(self, *arg, **kwarg)

    locked_method.__name__ = '%s(%s)' % ('lock_method', method.__name__)
    locked_method.__is_locked = True
    return locked_method


def make_threadsafe(cls, methodnames, lockfactory):
    init = cls.__init__

    def newinit(self, *arg, **kwarg):
        init(self, *arg, **kwarg)
        self._lock = lockfactory()

    cls.__init__ = newinit

    for methodname in methodnames:
        oldmethod = getattr(cls, methodname)
        newmethod = lock_method(oldmethod)
        setattr(cls, methodname, newmethod)

    return cls


def expose(func):
    return Pyro4.expose(lock_method(func))
