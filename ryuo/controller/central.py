#!/usr/bin/env python2
import logging
from threading import Lock
import signal
import sys

import Pyro4
from ryu.base import app_manager
from ryu.controller import dpset
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub
import ryu.lib.dpid as dpid_lib

from ryuo.common.app_lookup import AppLookupServer
from ryuo.common.rpc import RPCDaemon
from ryuo.config import RYUO_HOST
from ryuo.utils import config_logger, expose


Pyro4.config.REQUIRE_EXPOSE = True
Pyro4.config.SERIALIZER = 'pickle'
Pyro4.config.SERIALIZERS_ACCEPTED = {'json', 'marshal', 'serpent', 'pickle'}
Pyro4.config.THREADPOOL_SIZE = 160
Pyro4.config.HOST = RYUO_HOST


class Ryuo(app_manager.RyuApp):
    _NAME = None

    def __init__(self, *args, **kwargs):
        super(Ryuo, self).__init__(*args, **kwargs)
        self._setup_logger()
        self._rpc_daemon = None
        self.uri = None
        self.name = self._NAME
        self._local_apps_lock = Lock()
        self.local_apps = {}  # {dpid: ryu instance}
        self._rpc_thread = hub.spawn(self._run_rpc_daemon)
        self.threads.append(self._rpc_thread)

    def _setup_logger(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        config_logger(self._logger)
        self._logger.info('Starting')

    @expose
    def ryuo_register(self, uri):
        self._logger.info("App with uri %s connected.", uri)

    @expose
    def ryuo_unregister(self, uri):
        self._logger.info('App with uri %s leaves.', uri)

    @expose
    def ryuo_switch_enter(self, dpid, uri):
        self._logger.info('Switch %s comes up on uri: %s',
                          dpid_lib.dpid_to_str(dpid), uri)
        with self._local_apps_lock:
            self.local_apps[dpid] = Pyro4.Proxy(uri)

    @expose
    def ryuo_switch_leave(self, dpid, uri):
        self._logger.info('Switch %s leaves on uri %s.',
                          dpid_lib.dpid_to_str(dpid), uri)
        with self._local_apps_lock:
            del self.local_apps[dpid]

    def _run_rpc_daemon(self):
        self._rpc_daemon = RPCDaemon()
        self.uri = self._rpc_daemon.register(self)
        ns = AppLookupServer()
        ns.register(self.name, self.uri)
        self._logger.info('Ryuo running with name %s and uri %s.', self.name,
                          self.uri)
        self._rpc_daemon.requestLoop()
        self._logger.info('Request loop existing...')

    def close(self):
        # self._rpc_daemon.shutdown()
        for thread in self.threads:
            hub.kill(thread)

    @set_ev_cls(dpset.EventDP, dpset.DPSET_EV_DISPATCHER)
    def stub(self, evt):
        pass


original_sigint = signal.getsignal(signal.SIGINT)


def clean_up(signum, frame):
    global original_sigint
    signal.signal(signal.SIGINT, original_sigint)
    for app in app_manager.SERVICE_BRICKS.values():
        app.close()
    sys.exit()


signal.signal(signal.SIGINT, clean_up)