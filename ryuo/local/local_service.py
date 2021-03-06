import logging

import Pyro4
from ryu.base import app_manager
from ryu.controller import dpset, ofp_event
from ryu.controller.handler import set_ev_cls, MAIN_DISPATCHER, \
    CONFIG_DISPATCHER, HANDSHAKE_DISPATCHER
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_0, ofproto_v1_2, ofproto_v1_3, ofproto_v1_4
import ryu.lib.dpid as dpid_lib
from ryuo.common.app_lookup import AppLookupServer
from ryuo.common.rpc import RPCDaemon

from ryuo.utils import config_logger
from ryuo.config import RYU_HOST
from ryuo.local.ofctl import OfCtl


Pyro4.config.REQUIRE_EXPOSE = True
Pyro4.config.SERIALIZER = 'pickle'
Pyro4.config.SERIALIZERS_ACCEPTED = {'json', 'marshal', 'serpent', 'pickle'}
Pyro4.config.HOST = RYU_HOST


class LocalService(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION,
                    ofproto_v1_2.OFP_VERSION,
                    ofproto_v1_3.OFP_VERSION,
                    ofproto_v1_4.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LocalService, self).__init__(*args, **kwargs)
        self._setup_logger()
        self._rpc_thread = None
        self.dp = None
        self.uri = None
        self.ryuo_name = self.__class__.__name__
        self.app_name = None
        self.name = self.__class__.__name__

        self._rpc_daemon = RPCDaemon()
        self.uri = self._rpc_daemon.register(self)
        self._ns = AppLookupServer()
        self.ryuo = self._ns.lookup(self.ryuo_name)
        self._logger.info('%s host found', self.ryuo_name)
        self.ryuo.ryuo_register(self.uri)
        self._rpc_thread = hub.spawn(self._run_rpc_daemon)
        self.threads.append(self._rpc_thread)

    def close(self):
        self.ryuo.ryuo_unregister(self.uri)
        self._rpc_daemon.shutdown()
        self._rpc_daemon = None
        hub.joinall(self.threads)

    def _run_rpc_daemon(self):
        self._rpc_daemon.requestLoop()

    def _switch_enter(self, dp):
        self.app_name = "%s-%d" % (self.__class__.__name__, dp.id)
        self._ns.register(self.app_name, self.uri)
        self._setup_logger(dp.id)
        self.dp = dp
        self.ofctl = OfCtl.factory(dp, self._logger)
        self._logger.info('Switch entered, ready to work')

        self.ryuo.ryuo_switch_enter(dp.id, self.uri)

    def _switch_leave(self):
        self.ryuo.ryuo_switch_leave(self.dp.id, self.uri)
        self._ns.remove(self.app_name)
        self.app_name = None
        self.ofctl = None
        self.dp = None

    def _setup_logger(self, dpid=None):
        if dpid is None:
            dpid = '?'
        else:
            dpid = dpid_lib.dpid_to_str(dpid)
        self._logger = logging.getLogger(
            self.__class__.__name__ + ' ' + dpid)
        config_logger(self._logger)

    @set_ev_cls(dpset.EventDP, dpset.DPSET_EV_DISPATCHER)
    def datapath_handler(self, ev):
        if ev.enter:
            self._switch_enter(ev.dp)
        else:
            self._switch_leave()

    @set_ev_cls(ofp_event.EventOFPErrorMsg,
                [HANDSHAKE_DISPATCHER, CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def error_msg_handler(self, ev):
        msg = ev.msg
        self._logger.error('OFPErrorMsg: type=0x%02x code=0x%02x',
                           msg.type, msg.code)
