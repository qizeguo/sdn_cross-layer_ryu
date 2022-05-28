__author__ = 'root'

import os
from operator import attrgetter
import time

import logging
# from ryu import cfg
import networkx as nx
import json

from webob import Response
from ryu.app.wsgi import ControllerBase, WSGIApplication
from ryu.app.wsgi import route

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER

from ryu.ofproto import ofproto_v1_0, ofproto_v1_3
from ryu.ofproto import ofproto_v1_0_parser, ofproto_v1_3_parser
from ryu.ofproto import ether
from ryu.topology import switches
from ryu.topology import event

from ryu.lib import hub
from ryu.lib.packet import packet, ethernet

from ryu.app.domain_reply_controller import DomainReplyController

from ryu.app.domainTopo import DomainTopo
from ryu.app.switch_features import SwitchFeatures, PortFeatures
from ryu.app.queue_qos import QueueQos
from ryu.controller.event import arpevent
from ryu.controller.event import mactoportEvent
from ryu.app.arp import IcmpResponder
from ryu.app.domain_task import TaskList
from ryu.app.labelsManager import MplsLabelsPool
from ryu.app.queue_qos import QueuePort

DOMAINCONTROLLER = 'domainController'
DOMAINURLBASE = '/domain'
super_url_no_return = '/super/noreturn'
test_instance = 'test_instance'
DOMAINREPLYCONTROLLER = 'domainReplyController'

DOMAINID = 'domainId'
DPID = 'dpid'
RETURN = 'return'
TYPE = 'type'
SRC_SWITCH = 'srcSwitch'
DST_SWITCH = 'dstSwitch'
SRC_PORT = 'srcPort'
DST_PORT = 'dstPort'
SRC_MAC = 'srcMac'
DST_MAC = 'dstMac'
SRC_IP = 'srcIp'
DST_IP = 'dstIp'
COLLECTTIME = 'ctime'

TASK_ID = 'taskId'
PATHTYPE = 'pathType'

PORTSTATS = 'ports'
SWITCHFEATURE = 'features'

DOMAINWSGIIP = 'domainWsgiIp'
DOMAINWSGIPORT = 'domainWsgiPort'
NEXT_MAC = 'next_mac'
LOCAL_MAC = 'local_mac'
LAST_OUTPORT_NUM = 'last_outport_num'
PATHLIST='pathList'

LOG = logging.getLogger(__name__)

DEFAULTOVSDBADDR = '6640'

# CONF = cfg.CONF
#
# CONF.register_cli_opts([
#     cfg.BoolOpt('observe-links', default=True,
#                help='observe link discovery events.'),
#     cfg.IntOpt('domain_id', default=None,
#                help='the identifle of this domain controller'),
#     cfg.StrOpt('super_wsgi_IP', default='x.x.x.x',
#               help='Ip address of super\'s wsgi'),
#     cfg.IntOpt('super_wsgi_port', default=8080,
#               help='port no of super\'s wsgi'),
#     cfg.BoolOpt('super_exist', default=False,
#                 help='to notification whether super controller exists'),
#     cfg.BoolOpt('moniter_thread_flag', default=False,
#                 help='start a thread to get ports status')
# ])




class DomainController(app_manager.RyuApp):

    _CONTEXTS = {'wsgi': WSGIApplication,
                 'switches': switches.Switches,
                 'arp': IcmpResponder}

    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION, ofproto_v1_3.OFP_VERSION]


    def __init__(self, *args, **kwargs):
        super(DomainController, self).__init__(*args, **kwargs)

        self.domainId = self.CONF.domain_id
        self.name = 'domain_controller'
        self.domainWsgiIp = self.CONF.domain_wsgi_ip
        self.domainWsgiPort = self.CONF.domain_port
        self.topo = DomainTopo(name='Domain '+str(self.domainId))
        self.dps = {}
        self.switches = []
        self.sleep = 10

        self.TASK_LIST = {}
        self.LabelsPool = MplsLabelsPool()
        self.LabelsPool.initPool()
        self.deviceInfo = {}
        self.num = 0

        self.border_table = []
        self.arp_table = {}
        self.port_to_localmac = {}
    ############################################
        self.edgePort = []
        self.borderPeer = []
        self.outDomainSwitch = {}
        self.shortestPath = {}
        # self.shortestPath = {(513,518):[513,515,518],(518,513):[518,515,513]}
    #####################################################

        self.QoS_dict = {}
        self.superExist = self.CONF.super_exist
        if self.superExist:
            self.superWsgiIp = self.CONF.super_wsgi_ip
            self.superWsgiPort = self.CONF.super_wsgi_port

        self.superLastEcho = time.time()

        self.monitorThreadFlag = self.CONF.monitor_thread_flag
        #if self.monitorThreadFlag:
        #self.monitorThread = hub.spawn(self._monitor)
        self.lastCollect = {}

        self.keepAliveThread = hub.spawn(self._keepAlive)

        wsgi = kwargs['wsgi']
        data = {}
        data[DOMAINCONTROLLER] = self
        data[DomainReplyController] = DomainReplyController()
        wsgi.register(DomainWsgiController, data)

    def _get_QueueQos(self, dpid):
        assert dpid in self.QoS_dict
        return self.QoS_dict[dpid]

    def _get_datapath(self, dpid):
        assert dpid in self.dps
        return self.dps[dpid]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        self.logger.debug('switch features ev %s', msg)

        dpid = datapath.id

        switch = self.deviceInfo.setdefault(dpid, SwitchFeatures(dpid))

        switch.initFieds(msg.version, msg.capabilities, msg.n_buffers, msg.n_tables, msg.auxiliary_id)

        if dpid not in self.QoS_dict:
            queueQoSInstance = QueueQos(datapath, self.CONF)
            self.QoS_dict[dpid] = queueQoSInstance
            ip = datapath.address[0]
            ovs_addr = 'tcp:' + ip + ':' + DEFAULTOVSDBADDR
            queueQoSInstance.set_ovsdb_addr(dpid, ovs_addr)
            self.logger.info("QueueQoS Entering. dpid: %016x, addr: %s" % (dpid, ovs_addr))

#msg:  {'body': [OFPPort(port_no=9,hw_addr='48:6e:73:02:03:08',
# name='ge-1/1/9',config=0,state=1,curr=10240

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, CONFIG_DISPATCHER)
    def multipart_reply_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        switch = self.deviceInfo.setdefault(dpid, SwitchFeatures(dpid))

        # self.num = self.num+1
        # print self.num
        #ports = switch.getPorts()
        #print 'msg: ', msg.__dict__
        for portdesc in msg.body:
            #print 'portdesc: ', portdesc

            portNo = portdesc.port_no
            if portNo > 10000:
               # print 11111111111111111111111111
                name = portdesc.name
                switch.setName(name)
            else:
                port = PortFeatures(portNo)
                port.initFields(portdesc)
                #print 'port: ',port.__dict__
                switch.ports[portNo] = port
                self.QoS_dict[dpid].queueInfo[portNo] = QueuePort(portNo,dpid)


        if self.superExist:
            self._send_switch_features_message(dpid)

    def _send_switch_features_message(self, dpid):

        send_message = self._make_switch_features_message(dpid)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    def _make_switch_features_message(self, dpid):
        assert dpid in self.deviceInfo
        switchFeaturs = self.deviceInfo[dpid]
        info = switchFeaturs.makeFeaturesMessage()
        to_send = {}
        to_send[TYPE] = 'switchFeature'
        to_send[DOMAINID] = self.domainId
        to_send[DPID] = dpid
        to_send[SWITCHFEATURE] = info

        send_message = json.dumps(to_send)
        return send_message


    def remove_flow(self, datapath, match):

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        if ofproto.OFP_VERSION == ofproto_v1_0.OFP_VERSION:
            mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE,
                                    out_port=ofproto.OFPP_ANY, match=match)
        elif ofproto.OFP_VERSION == ofproto_v1_3.OFP_VERSION:
            mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE,
                                    out_group=ofproto.OFPG_ANY,out_port=ofproto.OFPP_ANY,
                                    match=match)

        datapath.send_msg(mod)

    def _get_ofproto_info(self, dpid):
        if dpid in self.dps:
            dp = self.dps[dpid]
            parser = dp.ofproto_parser
            ofproto = dp.ofproto
            return dp, parser, ofproto

    def _get_flow_mod(self, dpid, match, actions, priority=None, instruction=None):

        dp, parser, ofproto = self._get_ofproto_info(dpid)

        if not priority:
            priority = ofproto.OFP_DEFAULT_PRIORITY

        if ofproto.OFP_VERSION == ofproto_v1_3.OFP_VERSION:
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=inst)
        else:
            raise ValueError('We only support OpenFlow 1.3 now')
        return mod

    def _send_flow(self, datapath, mod):
        datapath.send_msg(mod)

    def pushMplsFlow(self, dpid, pushLabel, srcIp, dstIp, outPortNo, queueId, pathType, src_mac,dst_mac):
        assert dpid in self.dps

        dp, parser, ofproto = self._get_ofproto_info(dpid)
        eth_IP = ether.ETH_TYPE_IP
        eth_MPLS = ether.ETH_TYPE_MPLS
        #print 'srcIp,dstIp: ',srcIp,dstIp
        match = parser.OFPMatch(eth_type=eth_IP,ipv4_src=srcIp,ipv4_dst=dstIp)
        #match = parser.OFPMatch(eth_type=eth_IP,ipv4_src=('10.108.92.0','255.255.255.0'),
        #                        ipv4_dst=('10.108.93.0','255.255.255.0'))
        actions = []
        actions.append(parser.OFPActionSetField(eth_src=src_mac))
        actions.append(parser.OFPActionSetField(eth_dst=dst_mac))
        actions.append(parser.OFPActionPushMpls(eth_MPLS))
        f = parser.OFPMatchField.make(ofproto.OXM_OF_MPLS_LABEL, pushLabel)
        actions.append(parser.OFPActionSetField(f))
        actions.append(parser.OFPActionSetQueue(queueId))
        actions.append(parser.OFPActionOutput(outPortNo))

        mod = self._get_flow_mod(dpid, match, actions)
        if pathType == 'main':
            self._send_flow(dp, mod)
        elif pathType == 'backup':
            self.logger.info("Backup path's First switch should not install flow now!")

        return match, mod

    def popMplsFlow(self, dpid, popLabel, outPort, queueId):
        dp, parser, ofproto = self._get_ofproto_info(dpid)
        eth_IP = ether.ETH_TYPE_IP
        eth_MPLS = ether.ETH_TYPE_MPLS
        match = parser.OFPMatch(eth_type=eth_MPLS, mpls_label=popLabel)

        actions =[]
        actions.append(parser.OFPActionPopMpls(eth_IP))
        actions.append(dp.ofproto_parser.OFPActionSetQueue(queueId))
        actions.append(parser.OFPActionOutput(outPort))

        mod = self._get_flow_mod(dpid, match, actions)

        self._send_flow(dp, mod)
        return match, mod

    def swapMplsFlow(self, dpid, pushLabel, popLabel, outPortNo, queueId):
        dp, parser, ofproto = self._get_ofproto_info(dpid)
        eth_IP = ether.ETH_TYPE_IP
        eth_MPLS = ether.ETH_TYPE_MPLS
        match = parser.OFPMatch(eth_type=eth_MPLS, mpls_label=popLabel)

        actions = []
        actions.append(parser.OFPActionPopMpls(eth_IP))
        actions.append(parser.OFPActionPushMpls(eth_MPLS))
        f = parser.OFPMatchField.make(ofproto.OXM_OF_MPLS_LABEL, pushLabel)
        actions.append(parser.OFPActionSetField(f))
        actions.append(parser.OFPActionSetQueue(queueId))
        actions.append(parser.OFPActionOutput(outPortNo))

        mod = self._get_flow_mod(dpid, match, actions)

        self._send_flow(dp, mod)
        return match, mod

    def noMplsFlow(self, dpid, srcIp, dstIp, outPortNo, queueId, pathType):
        dp, parser, ofproto = self._get_ofproto_info(dpid)
        eth_IP = ether.ETH_TYPE_IP
        #eth_MPLS = ether.ETH_TYPE_MPLS
        match = parser.OFPMatch(eth_type=eth_IP, ipv4_src=srcIp, ipv4_dst=dstIp)

        actions = []

        actions.append(parser.OFPActionSetQueue(queueId))
        actions.append(parser.OFPActionOutput(outPortNo))

        mod = self._get_flow_mod(dpid, match, actions)

        if pathType == 'main':
            self._send_flow(dp, mod)
        elif pathType == 'backup':
            self.logger.info("Backup path's First switch should not install flow now!")

        return match, mod


    def popMplsMacFlow(self, dpid, popLabel, outPortNo, local_mac, next_mac, queueId):
        dp, parser, ofproto = self._get_ofproto_info(dpid)
        eth_IP = ether.ETH_TYPE_IP
        eth_MPLS = ether.ETH_TYPE_MPLS
        match = parser.OFPMatch(eth_type=eth_MPLS, mpls_label=popLabel)

        actions =[]
        #actions_inst = []
        actions.append(parser.OFPActionPopMpls(eth_IP))
        actions.append(dp.ofproto_parser.OFPActionSetQueue(queueId))
        #local_mac = self.port_to_localmac[outPortNo]
        #print 'local_mac,next_mac: ',local_mac,next_mac
        #actions.append(parser.OFPActionSetField(eth_src=local_mac))  ##
        #actions.append(parser.OFPActionSetField(eth_dst=next_mac))

        actions.append(parser.OFPActionOutput(outPortNo))
        #inst = parser.OFPInstructionGotoTable(2)
        #actions_inst.append(inst)
        mod = self._get_flow_mod(dpid, match, actions)
        #print 'mod: ', mod.__dict__
        self._send_flow(dp, mod)
        return match, mod  ####

    def noMplsMacFlow(self, dpid, srcIp, dstIp, outPortNo, local_mac, next_mac, queueId, pathType):

        dp, parser, ofproto = self._get_ofproto_info(dpid)
        eth_IP = ether.ETH_TYPE_IP
        #eth_MPLS = ether.ETH_TYPE_MPLS
        match = parser.OFPMatch(eth_type=eth_IP, ipv4_src=srcIp, ipv4_dst=dstIp)

        actions = []
        #actions_inst = []

        #local_mac = self.port_to_localmac[outPortNo]
        actions.append(parser.OFPActionSetField(eth_src=local_mac))  ##
        actions.append(parser.OFPActionSetField(eth_dst=next_mac))
        actions.append(parser.OFPActionSetQueue(queueId))
        actions.append(parser.OFPActionOutput(outPortNo))
        #inst = (parser.OFPInstructionGotoTable(2))
        mod = self._get_flow_mod(dpid, match, actions)

        if pathType == 'main':
            self._send_flow(dp, mod)
        elif pathType == 'backup':
            self.logger.info("Backup path's First switch should not install flow now!")

        return match, mod


    @set_ev_cls(event.EventSwitchEnter, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def switchEnterHandler(self, ev):
        switch = ev.switch
        dp = switch.dp
        dpid = dp.id
        if dpid not in self.switches:
            self.switches.append(dpid)

        if dpid not in self.dps:
            self.dps[dpid] = dp

        assert len(self.switches) == len(self.dps)

        self.topo.addNode(dpid)
        self.logger.info("Switch %d enter in local topo", dpid)

        if self.superExist:
            self._send_switch_enter_msg(dpid)
            self.logger.info("To super controller: Switch Enter->dpid %d", dpid)

    def _send_switch_enter_msg(self, dpid):
        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[DPID] = dpid
        to_send[TYPE] = 'switchEnter'
        send_message = json.dumps(to_send)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)


    @set_ev_cls(event.EventSwitchLeave, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def switchLeaveHandler(self, ev):
        switch = ev.switch
        dp = switch.dp
        dpid = dp.id

        if dpid in self.switches:
            self.switches.remove(dpid)
        if dpid in self.dps:
            del self.dps[dpid]

        if dpid not in self.topo.nodes():
            self.logger.warning("Switch %d not in local topo", dpid)
        else:
            self.topo.removeNode(dpid)
            self.logger.info("Switch %d leave the local topo", dpid)

        if self.superExist:
            self._send_switch_leave_msg(dpid)
            self.logger.info("To super controller: Switch Enter->dpid %d", dpid)

    def _send_switch_leave_msg(self, dpid):
        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[TYPE] = 'switchLeave'
        to_send[DPID] = dpid
        send_message = json.dumps(to_send)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    @set_ev_cls(event.EventLinkAdd, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def linkAddHandler(self, ev):
        link = ev.link
        src = link.src
        dst = link.dst
        src_switch = src.dpid
        dst_switch = dst.dpid
        src_port = src.port_no
        dst_port = dst.port_no
        #print 'src_switch: ',src_switch,type(src_switch)
        edge = (src_switch, dst_switch)

    ########################################################################
        if src_switch in self.dps:
            if edge not in self.topo.edges():
                self.topo.addEdge(src_switch, src_port, dst_switch, dst_port)
                self.logger.info("Link add: src %d port_no %8d-> dst %d %8d" % (src_switch, src_port,
                                                                                      dst_switch, dst_port))

        else:
            assert src_switch not in self.dps
            print "src_switch:",src_switch
            print "outdomian:",self.outDomainSwitch
            #self.outDomainSwitch[(dst_switch, dst_port)] = (src_switch, src_port)
            if src_switch not in self.outDomainSwitch.values():
                self.outDomainSwitch[dst_switch] = src_switch
                self.topo.addEdge(src_switch, src_port, dst_switch, dst_port)
                self.reportPath()
                dst_switch = str(dst_switch)

    #####################################################################################

        if self.superExist:
                self._send_link_add_msg(src_switch, src_port, dst_switch, dst_port)
                dst_switch = int(dst_switch)
                self.logger.info("TO Super controller.Link add: src %d port_no %8d-> dst %d %8d" %
                             (src_switch, src_port, dst_switch, dst_port))

    def _send_link_add_msg(self, ss, sp, ds, dp):

        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[TYPE] = 'linkAdd'
        to_send[SRC_SWITCH] = ss
        to_send[SRC_PORT] = sp
        to_send[DST_SWITCH] = ds
        to_send[DST_PORT] = dp

        send_message = json.dumps(to_send)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    @set_ev_cls(event.EventLinkDelete, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def linkDelHandler(self, ev):
        link = ev.link
        src = link.src
        dst = link.dst
        src_switch = src.dpid
        dst_switch = dst.dpid
        src_port = src.port_no
        dst_port = dst.port_no

        edge = (src_switch, dst_switch)
        if edge in self.topo.edges():
            self.topo.removeEdge(src_switch, src_port, dst_switch, dst_port)
            self.logger.info("Link delete: src %d port_no %8d-> dst %d port_no %8d" % (src_switch, src_port,
                                                                                           dst_switch, dst_port))

        if self.superExist:
            self._send_link_delete_msg(src_switch, src_port, dst_switch, dst_port)
            self.logger.info("TO Super controller.Link Delete: src %d port_no %8d-> dst %016x %8d" %
                             (src_switch, src_port, dst_switch, dst_port))

    def _send_link_delete_msg(self, ss, sp, ds, dp):

        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[TYPE] = 'linkDelete'
        to_send[SRC_SWITCH] = ss
        to_send[SRC_PORT] = sp
        to_send[DST_SWITCH] = ds
        to_send[DST_PORT] = dp

        send_message = json.dumps(to_send)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    def _monitor(self):
        hub.sleep(5)
        while True:

            for k in self.dps.keys():
                # self._request_stats(dp)
                self._request_stats(self.dps[k])
            hub.sleep(self.sleep)

    def _request_stats(self, datapath):
        self.logger.info('send stats request: %d', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    def _keepAlive(self):
        while True:
            if self.superExist:
                self._send_keep_alive_message()
                self.logger.info("send keep alive")
            hub.sleep(5)


    def _send_keep_alive_message(self):
        to_send = {}
        to_send[TYPE] = 'keepAlive'
        to_send[DOMAINID] = self.domainId
        to_send[DOMAINWSGIIP] =self.domainWsgiIp
        to_send[DOMAINWSGIPORT] = self.domainWsgiPort

        send_message = json.dumps(to_send)
        #print send_message
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body
        self.logger.info('datapath         in_port  eth_dst  out_port packets  bytes    ')
        self.logger.info('---------------- -------- -------- -------- -------- -------- ')
        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match['in_port'],
                                             flow.match['eth_dst'])):
            self.logger.info('%016x %8x %17s %8x %8d %8d',
                             ev.msg.datapath.id, stat.match['in_port'],
                             stat.match['eth_dst'], stat.instructions[0].actions[0].port,
                             stat.packet_count, stat.byte_count)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        msg = ev.msg
        body = msg.body
        dpid = msg.datapath.id
        switchCollect = self.lastCollect.setdefault(dpid, SwitchStats(dpid))
        ports = switchCollect.getPotrs()

        self.logger.info('datapath            port     '
                         'rx-pkts   rx-bytes   rx-error'
                         'tx-pkts   tx-bytes   tx-error')
        self.logger.info('-----------    --------------'
                         '-------   --------   --------'
                         '-------   --------   --------')
        for stat in sorted(body, key=attrgetter('port_no')):
            self.logger.info('%016x %8x %8d %8d %8d %8d %8d %8d ',
                             ev.msg.datapath.id, stat.port_no,
                             stat.rx_packets, stat.rx_bytes, stat.rx_errors,
                             stat.tx_packets, stat.tx_bytes, stat.tx_errors)

        for stat in sorted(body, key=attrgetter('port_no')):
            portNo = stat.port_no
            if portNo < 10000:
                port = ports.setdefault(portNo, Portstats(portNo))
                port.setFieds(stat, time.time())

        if self.superExist:
            pass
            # self._send_port_stats(dpid)

    def _send_port_stats(self, dpid):

        send_message = self._make_port_stats_message(dpid)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)



    def _make_port_stats_message(self, dpid):
        assert dpid in self.lastCollect
        switchCollect = self.lastCollect[dpid]
        portsMsg = switchCollect.getPortMessageByRx_bytes()
        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[TYPE] = 'portStats'
        to_send[DPID] = dpid
        to_send[PORTSTATS] = portsMsg
        send_message = json.dumps(to_send)

        # print send_message
        return send_message


    def sendTaskAssignReply(self, taskId, pathType):
        self.logger.info("send Task Assign Reply")
        send_message = self._make_task_assign_reply(taskId, pathType)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    def _make_task_assign_reply(self, taskId, pathType):
        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[TYPE] = 'taskAssignReply'
        to_send[TASK_ID] = taskId
        to_send[PATHTYPE] = pathType

        send_message = json.dumps(to_send)
        return send_message

    def sendTaskDeleteReply(self, taskId):
        self.logger.info("send Task Delete Reply")
        send_message = self._make_task_delete_reply(taskId)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    def _make_task_delete_reply(self, taskId):
        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[TYPE] = 'taskDeleteReply'
        to_send[TASK_ID] = taskId

        send_message = json.dumps(to_send)
        return send_message

    def _to_commad(self, send_message, returnType=False):

        command = 'curl -X '
        if returnType:
            command += 'GET -d \''
        else:
            command += 'PUT -d \''
        command += send_message
        command += '\' http://'
        command += self.superWsgiIp
        command += ':'
        command += str(self.superWsgiPort)
        command += super_url_no_return
        command += ' 2> /dev/null'
        return command

    # @staticmethod
    def send_no_return_command(self, command):
        #print 'command: ',command
        os.popen2(command)
        # print "to_print:", to_print


    @set_ev_cls(arpevent, dispatchers=None)
    def arp_handler(self, ev):

        ev_dict = self.object2dict(ev)

        self.borderPeer.extend(ev.dpid_table)
        self.borderPeer = list(set(self.borderPeer))
        self.reportPath()

        self.port_to_localmac = ev_dict['port_to_localmac']
        self.arp_table.update(ev_dict['ip_to_mac'])
        ev_dict[TYPE] = 'ArpMessage'
        #print ev_dict
        send_msg = json.dumps(ev_dict)
        command = self._to_commad(send_msg)
        self.send_no_return_command(command)
        #print 12333333333333333333

    @set_ev_cls(mactoportEvent, dispatchers=None)
    def mac_to_port_handler(self,ev):
        ev_dict = self.object2dict(ev)
        ev_dict[TYPE] = 'mactoportmessage'
        send_msg = json.dumps(ev_dict)
        command = self._to_commad(send_msg)
        self.send_no_return_command(command)



    def object2dict(self,obj):
        d={}
        d['__class__'] = obj.__class__.__name__
        d['__module__'] = obj.__module__
        d.update(obj.__dict__)
        return d


    def reportPath(self):
        self.edgePort = list(set(self.borderPeer) | set(self.outDomainSwitch.keys()))
        tmpPathList = self.pathAnalysisByShortest(self.edgePort)
        self._send_path_report_msg(tmpPathList)
        #print "self.edgePort:" , self.edgePort
        #print "tmpPathList:" , tmpPathList
        #print 'tmpPathList: ',tmpPathList
    ###############################################


    def pathAnalysisByShortest(self, edgePort):
        pathList=[]
        if edgePort is None:
            LOG.info("This Domain have no edgePort!")
            return None
        # if len(edgePort) == 0 or len(edgePort) == 1:
        #     return
        print edgePort
        for i in edgePort:
            for m in edgePort:
                if i == m:
                    continue
                tmppath = self.topo.getShortestPath(i, m)
                pathList.append([i, m, len(tmppath)-1])
                self.shortestPath[(i, m)] = tmppath

        self.logger.info('in_switch          out_switch        length    ')
        self.logger.info('----------------  ----------------  -------- ')

        for stat in pathList:
            if len(stat) > 2:
                pass
                #print ('%016x %016x %8d'%(stat[0], stat[1], stat[2]))
        self.logger.info("pathList end")
        # print "self.edgePort", self.edgePort
        # print "self.borderPeer", self.borderPeer
        # print "self.outDomainSwitch",self.outDomainSwitch
        # print "self.topoe.dges:",self.topo.edges()
        # print "self.topo.nodes:",self.topo.nodes()
        
        #print 'self.shortestPath: ', self.shortestPath
        return pathList

    def _send_path_report_msg(self, pathList):
        #self.logger.info("send Path Report Msg")
        send_message = self._make_path_report_msg(pathList)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)

    def _make_path_report_msg(self, pathList):
        to_send = {}
        to_send[DOMAINID] = self.domainId
        to_send[TYPE] = 'pathReport'
        to_send[PATHLIST] = pathList
        send_message = json.dumps(to_send)
        return send_message


    #################################################################

class DomainWsgiController(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(DomainWsgiController, self).__init__(req, link, data, **config)
        self.name = 'I am Domain Wsgi Controller'

        # self.test = data[test_instance]
        self.domainController = data[DOMAINCONTROLLER]
        self.domainReplyController = data[DomainReplyController]

        if hasattr(self.__class__, 'LOGGER_NAME'):
            self.logger = logging.getLogger(self.__class__.LOGGER_NAME)
        else:
            self.logger = logging.getLogger(self.name)

    @route('domain', DOMAINURLBASE + '/noreturn', methods=['PUT'], requirements=None)
    def noreturned_command_hanlder(self, req):
        msgbody = eval(req.body)
        type = msgbody[TYPE]
        try:
            func = getattr(self.domainReplyController, type)
        except:
            self.logger.fatal("no such type")

        func(msgbody, self.domainController)

    @route('domain', DOMAINURLBASE + '/return', methods=['PUT'], requirements=None)
    def returned_command_handler(self, req):
        msgbody = eval(req.body)
        type = msgbody[TYPE]

        func = getattr(self.domainReplyController, type)

        return_msg = func(msgbody, self.DomainController)
        return Response(status=400, body=return_msg)

    # @route('domain', '/super/noreturn', methods=['PUT'], requirements=None)
    # def test(self, req):
    #     #print eval(req.body)


    @route('domain','/domain/test1',methods=['PUT'],requirements=None)
    def test1(self,req):
        msg=eval(req.body)

        #print msg["type"]
    # @route('domain', '/super/noreturn', methods=['GET'], requirements=None)
    # def test1(self, req):
    #     self.domainController.send_flow_stats_request(513)

class SwitchStats(object):

    def __init__(self, dpid):
        self.dpid = dpid
        self.ports = {}

    def getPotrs(self):
        return self.ports

    def getPort(self, portNo):
        ports = self.getPotrs()
        assert portNo in ports
        return ports[portNo]

    def getPortMessageByRx_bytes(self):
        message = {}
        for portNo in self.ports:
            portx = self.getPort(portNo)
            rx_bytes = portx.getRx_bytes()
            message[portNo] = rx_bytes

        return message



class Portstats(object):

    def __init__(self, portNo, *args, **kwargs):
        self.portNo = portNo
        self.rx_packets = 0
        self.rx_bytes = 0
        self.rx_errors = 0
        self.tx_packets = 0
        self.tx_bytes = 0
        self.tx_errors = 0

        self.collectTime = time.time()

        self.rx_bytes_gap = 0

    def _set_rx_bytes_gap(self, stat):
        speed = stat.rx_bytes - self.rx_bytes
        self.rx_bytes_gap = speed


    def setFieds(self, stat, timeNow):

        self._set_rx_bytes_gap(stat)
        self.rx_packets = stat.rx_packets
        self.rx_bytes = stat.rx_bytes
        self.rx_errors = stat.rx_errors
        self.tx_packets = stat.tx_packets
        self.tx_bytes = stat.tx_bytes
        self.tx_errors = stat.tx_errors
        self.collectTime = timeNow

    def getRx_bytes(self):
        return self.rx_bytes_gap
