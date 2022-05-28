from ryu.base import app_manager

from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls

from ryu.ofproto import ofproto_v1_3

from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import icmp

from ryu.controller import event


class IcmpResponder(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(IcmpResponder, self).__init__(*args, **kwargs)
        # self.hw_addr = '00:1b:78:57:6d:38'
        # self.ip_addr = ['10.108.91.100', '10.108.92.100','10.108.93.100']
        #'10.108.93.100' is the ip address of local network
        self.dpid_table = []
        #self.handler_ip = {}
        self.arp_table = {'10.108.91.100':'00:1b:78:57:6d:38', '10.108.92.100':'00:1b:78:57:6d:38',
                          '10.108.93.100':'00:00:00:00:00:01', '10.108.93.101':'00:00:00:00:00:02'}
        #arp_table can be extended,but arp_table1 can't be extended.
        self.arp_table1 = {'10.108.91.100':'00:1b:78:57:6d:38', '10.108.92.100':'00:1b:78:57:6d:38',
                          '10.108.93.100':'00:00:00:00:00:01', '10.108.93.101':'00:00:00:00:00:02'}

        self.port_to_localmac = {}
        self.border_table = []
        self.gateway_ip = ['10.108.90.100', '10.108.90.101']

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(port=ofproto.OFPP_CONTROLLER,
                                          max_len=ofproto.OFPCML_NO_BUFFER)]

        inst = [parser.OFPInstructionActions(type_=ofproto.OFPIT_APPLY_ACTIONS,
                                             actions=actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=0,
                                match=parser.OFPMatch(), instructions=inst)
        datapath.send_msg(mod)

        if datapath.id == 513:

            actions1 = [parser.OFPActionOutput(port=5)]
            inst1 = [parser.OFPInstructionActions(type_=ofproto.OFPIT_APPLY_ACTIONS,
                                                 actions=actions1)]
            match1 = parser.OFPMatch(in_port=4, ip_proto=6, ipv4_src='10.108.92.1',
                                    eth_type=0x0800,ipv4_dst='10.108.92.100', tcp_dst=179)
            mod1 = parser.OFPFlowMod(datapath=datapath,priority=1, idle_timeout=0,
                                    match=match1, instructions=inst1)
            datapath.send_msg(mod1)

            actions2 = [parser.OFPActionOutput(port=4)]
            inst2 = [parser.OFPInstructionActions(type_=ofproto.OFPIT_APPLY_ACTIONS,
                                                 actions=actions2)]
            match2 = parser.OFPMatch(in_port=5, ip_proto=6, ipv4_src='10.108.92.100',
                                    eth_type=0x0800,ipv4_dst='10.108.92.1', tcp_src=179)
            mod2 = parser.OFPFlowMod(datapath=datapath, priority=2, idle_timeout=0,
                                    match=match2, instructions=inst2)
            datapath.send_msg(mod2)

            #print 1111111111111111111111111111


        #print datapath.id
#{'port_to_dpid': {5: 513}, '__module__': 'ryu.controller.event',
#'ip_to_port': {'10.108.91.1': 5}, 'ip_to_mac': {'10.108.91.1': '00:10:01:08:00:03'},
#'arp_extension_table': {513: {5: ['00:10:01:08:00:03', '10.108.91.1']}},
#'type': 'ArpMessage', '__class__': 'arpevent'}

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        port = msg.match['in_port']
        pkt = packet.Packet(data=msg.data)
        # return a packet object,with an ethernet object in the list of protocol

        #self.logger.info("packet-in %s" % (pkt,))
        pkt_ethernet = pkt.get_protocol(ethernet.ethernet)  #pkt_ethernet is an ethernet object with dst,src and type
        #print pkt_ethernet,111111111111111111
        if not pkt_ethernet:
            return
        pkt_arp = pkt.get_protocol(arp.arp)  #pkt_arp is an arp object with ip and mac address
        #print pkt_arp
        #if pkt_arp and (pkt_arp.src_ip,pkt_arp.dst_ip) not in self.handler_ip.items():
        if pkt_arp:
            #self.handler_ip[pkt_arp.src_ip] = pkt_arp.dst_ip
            self._handle_arp(datapath, port, pkt_ethernet, pkt_arp)
            self.send_arp_event(datapath, port, pkt_arp)
            return

        pkt_ipv4 = pkt.get_protocol(ipv4.ipv4)
        pkt_icmp = pkt.get_protocol(icmp.icmp)
        if pkt_icmp:
            self._handle_icmp(datapath, port, pkt_ethernet, pkt_ipv4, pkt_icmp)
            return

    def _handle_arp(self, datapath, port, pkt_ethernet, pkt_arp):
        if pkt_arp.opcode != arp.ARP_REQUEST:
            return
        if pkt_arp.dst_ip in self.arp_table:
            #index = self.arp_table.keys().index(pkt_arp.dst_ip)
            pkt = packet.Packet()
            pkt.add_protocol(ethernet.ethernet(ethertype=pkt_ethernet.ethertype,
                                    dst=pkt_ethernet.src, src=self.arp_table[pkt_arp.dst_ip]))
                                    # src and dst mac addresses

            pkt.add_protocol(arp.arp(opcode=arp.ARP_REPLY,
                                     src_mac=self.arp_table[pkt_arp.dst_ip], src_ip=pkt_arp.dst_ip,
                                     dst_mac=pkt_arp.src_mac, dst_ip=pkt_arp.src_ip)
                             )
            self._send_packet(datapath, port, pkt)
            if pkt_arp.dst_ip in self.arp_table1:
                self.port_to_localmac.update({port: self.arp_table1[pkt_arp.dst_ip]})
                print 'port_to_localmac: ', self.port_to_localmac
            print 'return ARP from', pkt_arp.src_ip


    def _handle_icmp(self, datapath, port, pkt_ethernet, pkt_ipv4, pkt_icmp):
        if pkt_icmp.type != icmp.ICMP_ECHO_REQUEST:
            return
        if pkt_ipv4.dst in self.arp_table1:
           # index = self.ip_addr.index(pkt_ipv4.dst)

            pkt = packet.Packet()
            pkt.add_protocol(ethernet.ethernet(ethertype=pkt_ethernet.ethertype,
                                           dst=pkt_ethernet.src, src=self.arp_table1[pkt_ipv4.dst]))
            pkt.add_protocol(ipv4.ipv4(dst=pkt_ipv4.src, src=pkt_ipv4.dst,
                                       proto=pkt_ipv4.proto))
            pkt.add_protocol(icmp.icmp(type_=icmp.ICMP_ECHO_REPLY,
                                       code=icmp.ICMP_ECHO_CODE, csum=0, datapath=pkt_icmp.data))
            self._send_packet(datapath, port, pkt)

    # def send_flow_stats_request(self,datapath):
    #     ofp = datapath.ofproto
    #     ofp_parser = datapath.ofproto_parser
    #     cookie = cookie_mask = 0
    #     #match = ofp_parser.OFPMatch()
    #     req = ofp_parser.OFPFlowStatsRequest(datapath,0,ofp.OFPTT_ALL,ofp.OFPP_ANY,
    #                                          ofp.OFPG_ANY,cookie,cookie_mask)
    #     datapath.send_msg(req)
    #
    # @set_ev_cls(ofp_event.EventOFPFlowStatsReply,MAIN_DISPATCHER)
    # def flow_stats_reply_handler(self,ev):
    #     flows = []
    #     for stat in ev.msg.body:
    #         flows.append('table_id=%s '
    #                      'duration_sec=%d '
    #                      'priority=%d '
    #                      'idle_timeout=%d hard_timeout=%d flags=0x%04x '
    #                      'cookie=%d packet_count=%d byte_count=%d '
    #                      'match=%s instructions=%s' %
    #                      (stat.table_id,
    #                       stat.duration_sec, stat.duration_nsec,
    #                       stat.priority,
    #                       stat.idle_timeout, stat.hard_timeout, stat.flags,
    #                       stat.cookie, stat.packet_count, stat.byte_count,
    #                       stat.match, stat.instructions))
    #     self.logger.debug('FlowStats: %s', flows)


    def _send_packet(self, datapath, port, pkt):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        pkt.serialize()
        self.logger.info("packet-out %s" % (pkt,))
        data = pkt.data
        actions = [parser.OFPActionOutput(port=port)]


        out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=ofproto.OFPP_CONTROLLER, actions=actions, data=data)
        datapath.send_msg(out)


    def send_arp_event(self, datapath, port, pkt_arp):
        ip_to_port = {pkt_arp.src_ip: port}  ######
        ip_to_mac = {pkt_arp.src_ip: pkt_arp.src_mac}  ########
        self.arp_table.update(ip_to_mac)
        ip_to_dpid = {pkt_arp.src_ip: datapath.id}  ######
        arp_extension_table = {datapath.id: {port: [pkt_arp.src_mac, pkt_arp.src_ip]}}  #######
        if datapath.id not in self.dpid_table:
            self.dpid_table.append(datapath.id)
        port_to_localmac = self.port_to_localmac
        dpid_table = self.dpid_table
        #print 'dpid_table: ',dpid_table
        ev = event.arpevent(ip_to_port, ip_to_mac, ip_to_dpid, arp_extension_table,
                            dpid_table, port_to_localmac)
        self.send_event('domain_controller', ev)



