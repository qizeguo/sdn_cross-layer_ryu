__author__ = 'root'

import httplib
import logging
import json
import random
from webob import Response
from ryu.base import app_manager
from ryu.app.wsgi import ControllerBase, WSGIApplication
from ryu.app.wsgi import route
from ryu.controller.handler import set_ev_cls, set_ev_handler,MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.l2topology.event import EventTopoRequest, EventTopoReply
from ryu.controller import  ofp_event
from ryu.topology import switches
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, lldp, arp, icmp
from ryu.lib import dpid as dpid_lib
import networkx as nx
from ryu.ofproto import ofproto_v1_0, ofproto_v1_3
from ryu.ofproto import ofproto_v1_0_parser, ofproto_v1_3_parser
from ryu.ofproto import ether
from ryu.l2topology.api import get_topo, get_port_to_switch
from ryu.database.api import display_deviceinfo
from ryu.database.deviceinfo import DEVICE_INFO
from ryu.l2topology.api import list_link_status
import time, os, sys
from ryu.controller import conf_switch
from ryu.app.conf_switch_key import  OVSDB_ADDR
from ryu.app.queueset import QueueQoSAPI
from ryu.app.testEvent import get_queue_info

test_instance = 'test_api_app'

traffic_url_base = '/traffic'
queue_url_base = '/queue'
mac_url_base = '/mac'
device_url_base = '/device'
path_url_base = '/path'

TRAFFICID_PATTERN=r'[0-9]{1,4}|all'
SWITCHID_PATTERN = dpid_lib.DPID_PATTERN + r'|all'

REST_SRC_MAC = 'src_mac'
REST_DST_MAC = 'dst_mac'
REST_DL_TYPE = 'dl_type'
REST_SRC_IP = 'nw_src'
REST_DST_IP = 'nw_dst'


REST_TRAFFIC_ID = 'id'
REST_SRC_SWITCH = 'src_switch'
REST_DST_SWITCH = 'dst_switch'
REST_MID_SWITCH = 'mid_switch'
REST_BANDTH = 'bandth'

REQUIREMENTS ={'trafficID':TRAFFICID_PATTERN,
               'switchid':SWITCHID_PATTERN,}

LOG = logging.getLogger(__name__)

class Test(app_manager.RyuApp):

    _CONTEXTS = {'wsgi':WSGIApplication,
                 'switches':switches.Switches,
                 'conf_switch': conf_switch.ConfSwitchSet,
                 }
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION, ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Test, self).__init__(*args, **kwargs)
        self.traffic = {}
        self.traffic_to_list = {}
        self.mac_to_port = {}
        self.ip_to_port = {}
        self.device_info={}
        self.sw = kwargs['switches']
        self.config = kwargs['conf_switch']
        wsgi = kwargs['wsgi']
        wsgi.register(TrafficController, {test_instance: self})
        
        
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        self.logger.debug('switch features ev %s', msg)

        dpid = datapath.id

        device_info = self.device_info.setdefault(dpid,{})
        device_info['dpid'] = dpid
        device_info['version'] = msg.version
        device_info['capabilities']= msg.capabilities
        device_info['n_buffers'] = msg.n_buffers
        device_info['n_tables'] = msg.n_tables
        device_info['auxiliary_id'] = msg.auxiliary_id

        if datapath.ofproto.OFP_VERSION < 0x04:
            port_info = device_info.setdefault('port',{})


    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, CONFIG_DISPATCHER)
    def multipart_reply_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        device_info = self.device_info[dpid]
        port_info = device_info.setdefault('port',{})

        for port in msg.body:
            port_no = port.port_no
            if port_no > 100000:
                device_info['name'] = port.name
            each_port_info = port_info.setdefault(port_no, {})
            each_port_info['port_no'] = port_no
            each_port_info['hw_addr'] = port.hw_addr
            each_port_info['name'] = port.name
            each_port_info['config'] = port.config
            each_port_info['state'] = port.state
            each_port_info['curr'] = port.curr
            each_port_info['advertiesd'] = port.advertised
            each_port_info['supported'] = port.supported
            each_port_info['peer'] = port.peer
            each_port_info['cur_speed'] = port.curr_speed
            each_port_info['max_speed'] = port.max_speed



    def add_flow(self, datapath, match, actions, priority=None, buffer_id=None):

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        if priority == None:
            priority = ofproto.OFP_DEFAULT_PRIORITY

        if ofproto.OFP_VERSION == ofproto_v1_0.OFP_VERSION:
            mod = parser.OFPFlowMod(datapath=datapath, match=match, cookie=0, priority=priority,
                                    command=ofproto.OFPFC_ADD, flags=ofproto.OFPFF_SEND_FLOW_REM,
                                    actions=actions)
        elif ofproto.OFP_VERSION == ofproto_v1_3.OFP_VERSION:
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)

        datapath.send_msg(mod)


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

    def push_mpls_flow(self, dpid, label, src_ip,dst_ip,eth_src, eth_dst, out_port, queue_id):
        dp = self.sw.dps[dpid]
        parser = dp.ofproto_parser
        ofproto = dp.ofproto
        eth_IP = ether.ETH_TYPE_IP
        eth_MPLS = ether.ETH_TYPE_MPLS
        if(src_ip and dst_ip and eth_src and eth_dst):
            match = ofproto_v1_3_parser.OFPMatch(eth_type=eth_IP, ipv4_src=src_ip, ipv4_dst=dst_ip,eth_src = eth_src,eth_dst=eth_dst)
        elif(eth_dst and eth_src):
            match = ofproto_v1_3_parser.OFPMatch(eth_type=eth_IP,eth_src = eth_src,eth_dst=eth_dst)
        else:
            match = ofproto_v1_3_parser.OFPMatch(eth_type=eth_IP, ipv4_src=src_ip, ipv4_dst=dst_ip)
        # match = ofproto_v1_3_parser.OFPMatch(eth_type=eth_IP,eth_dst=eth_dst)
        # match = parser.OFPMatch()
        # match.set_dl_type(eth_IP)
        # match.set_ipv4_src(src_ip)
        actions = []
        actions.append(parser.OFPActionPushMpls(eth_MPLS))
        f = parser.OFPMatchField.make(ofproto.OXM_OF_MPLS_LABEL, label)
        actions.append(parser.OFPActionSetField(f))
        actions.append(parser.OFPActionOutput(out_port))
        if  queue_id:
            actions.append(parser.OFPActionSetQueue(queue_id))

        self.add_flow(dp, match, actions)
        return match

    def pop_mpls_flow(self,dpid,label,out_port, queue_id):
        dp = self.sw.dps[dpid]
        parser = dp.ofproto_parser
        ofproto = dp.ofproto
        eth_IP = ether.ETH_TYPE_IP
        eth_MPLS = ether.ETH_TYPE_MPLS
        match = parser.OFPMatch( eth_type=eth_MPLS,mpls_label=label)

        actions=[]
        actions.append(parser.OFPActionPopMpls(eth_IP))
        if queue_id:
            actions.append(dp.ofproto_parser.OFPActionSetQueue(queue_id))
        actions.append(parser.OFPActionOutput(out_port))

        self.add_flow(dp, match, actions)
        return match

    def swap_mpls_flow(self, dpid, pop_label, push_label, out_port, queue_id):
        dp = self.sw.dps[dpid]
        parser = dp.ofproto_parser
        ofproto = dp.ofproto
        eth_IP = ether.ETH_TYPE_IP
        eth_MPLS = ether.ETH_TYPE_MPLS
        match = parser.OFPMatch( eth_type=eth_MPLS,mpls_label=pop_label)

        actions = []
        actions.append(parser.OFPActionPopMpls(eth_IP))
        actions.append(parser.OFPActionPushMpls(eth_MPLS))
        f = parser.OFPMatchField.make(ofproto.OXM_OF_MPLS_LABEL, push_label)
        actions.append(parser.OFPActionSetField(f))
        actions.append(parser.OFPActionOutput(out_port))
        if queue_id:
            actions.append(parser.OFPActionSetQueue(queue_id))


        self.add_flow(dp, match, actions)
        return match


class TrafficController(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(TrafficController, self).__init__(req, link, data, **config)
        self.test = data[test_instance]

    #curl -X PUT -d "{'id':'1', 'src_mac':'00:00:00:00:00:01', 'dst_mac':'00:00:00:00:00:03', 'nw_src':'10.0.0.1','nw_dst':'10.0.0.3','src_switch':0xeb74486e730201f7, 'dst_switch':0x2bff486e73020311, 'bandth':450000}"  http://localhost:8080/traffic/add
    @route('test',traffic_url_base+'/add', methods=['PUT'],requirements=None)
    def add_traffic(self, req, **kwargs):
        test = self.test
        traffic = test.traffic
        traffic_to_list = test.traffic_to_list
        mac_to_port = test.mac_to_port
        rest = eval(req.body)
        if REST_SRC_MAC in rest:
            src_mac = rest[REST_SRC_MAC]
        else:
            src_mac = None
        if REST_DST_MAC in rest:
            dst_mac = rest[REST_DST_MAC]
        else:
            dst_mac = None
        if REST_SRC_IP in rest:
            src_ip = rest[REST_SRC_IP]
        else:
            src_ip = None
        if REST_DST_IP in rest:
            dst_ip = rest[REST_DST_IP]
        else:
            dst_ip = None
        traffic_id=rest[REST_TRAFFIC_ID]
        LOG.info('The message of traffic %s message is %s' %(traffic_id, rest))

        if traffic_id in traffic.keys():
            body = {'result':'failure',
                    'detail':'duplited traffic id'}
            return Response(status=400, body=str(body) + '\n')

        src_switch = rest[REST_SRC_SWITCH]
        dst_switch = rest[REST_DST_SWITCH]
        if REST_BANDTH in rest:
            bandth = rest[REST_BANDTH]
        else:
            bandth = None

        tra = traffic.setdefault(traffic_id,{})
        tra_to_list = traffic_to_list.setdefault(traffic_id, {})

        switch_list = self.get_path(src_switch, dst_switch)

        LOG.info('path info is ' + str(switch_list))
        mpls_labels = label_distribute(switch_list)
        LOG.info('mpls_labels: ' +  str(mpls_labels))

        portInfo=get_port_to_switch(test)
        matchInfo = tra.setdefault('match',{})
        for switch in switch_list:
            if switch == src_switch:
                if bandth:
                    queue_id = self.get_queue_id(switch, bandth)
                    if queue_id == -1:
                        return Response(status=400, body='NO QUEUE!\n')
                    if queue_id == None:
                        return Response(status=400, body='NO SUITABLE QUEUE!\n')
                else:
                    queue_id = None

                push_label = mpls_labels[switch]['push']
                next_switch = switch_list[1]
                out_port = portInfo[switch][next_switch]['src_port_no']
                # src_ip = '10.0.0.1'
                match = test.push_mpls_flow(switch, push_label, src_ip,dst_ip, src_mac, dst_mac, out_port, queue_id)
            elif switch == dst_switch:
                if bandth:
                    queue_id = self.get_queue_id(switch, bandth)
                    if queue_id == -1:
                        return Response(status=400, body='NO QUEUE!\n')
                    if queue_id == None:
                        return Response(status=400, body='NO SUITABLE QUEUE!\n')
                else:
                    queue_id = None
                pop_label = mpls_labels[switch]['pop']
                if switch in mac_to_port.keys():
                    mac_dict = mac_to_port[switch]
                else:
                    rest = 'No mac_to_port info for switch %d' % switch
                    # return Response(status=400, body = rest + '\n')

                if dst_mac in mac_dict.keys():
                    out_port = mac_dict[dst_mac]
                    LOG.info('out_port')
                else:
                    rest = 'No out_port info for mac_address: %s' % dst_mac
                    # return Response(status=400, body= rest + '\n')
                match = test.pop_mpls_flow(switch, pop_label, 1, queue_id)

            else:
                if bandth:
                    queue_id = self.get_queue_id(switch, bandth)
                    if queue_id == -1:
                         return Response(status=400, body='NO QUEUE!\n')
                    if queue_id == None:
                         return Response(status=400, body='NO SUITABLE QUEUE!\n')
                else:
                    queue_id = None
                index = switch_list.index(switch)
                next_switch = switch_list[index + 1]
                out_port = portInfo[switch][next_switch]['src_port_no']
                push_label = mpls_labels[switch]['push']
                pop_label = mpls_labels[switch]['pop']
                match = test.swap_mpls_flow(switch, pop_label, push_label,out_port, queue_id)
            matchInfo[switch] = match
        tra_to_list['id'] = traffic_id
        creat_time_to_list = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        tra_to_list['creat_time'] = creat_time_to_list
        tra_to_list['path'] = switch_list
        creat_time_to_store = time.time()
        tra['creat_time'] = creat_time_to_store


        rest = {'result':'success',
                'detail':tra_to_list}
        return Response(status=400, body=str(rest) + '\n')

    # curl -X GET http://localhost:8080/traffic/list/{trafficID}
    @route('test', traffic_url_base + '/list/{trafficID}', methods=['GET'], requirements=REQUIREMENTS)
    def list_traffic(self, req, **kwargs):
        test = self.test
        if len(test.traffic_to_list) == 0:
            return Response(status=400, body='No traffic')

        ('1', {'path': [16966265335424614903L, 18277094301966140168L, 3170332301905232657L], 'creat_time': '2015-03-22 20:16:49', 'id': '1'})

        traffic_id = kwargs['trafficID']
        traffic_list = []
        message = 'Traffic Info:\n'
        if traffic_id =='all':
             for i in test.traffic_to_list.items():
                message = message +  "ID: " + i[1]['id'] + '\n'
                message = message + 'Creat_time:' + i[1]['creat_time'] + '\n'
                message = message + 'path: ' + str(i[1]['path']) + '\n'

        else:
            if traffic_id not in test.traffic_to_list.keys():
                rest = {'result':'failure',
                        'detail':'no such traffic'}
                return Response(status=400, body=str(rest))

            to_list = test.traffic_to_list[traffic_id]
            message = message +  "ID: " + to_list['id'] + '\n'
            message = message + 'Creat_time:' + to_list['creat_time'] + '\n'
            message = message + 'path: ' + str(to_list['path']) + '\n'
            # traffic_list.append(to_list)

        return Response(status=400, body=message)

    # curl -X DELETE http://localhost:8080/traffic/del/{trafficID}
    @route('test', traffic_url_base + '/del/{trafficID}', methods=['DELETE'],requirements=REQUIREMENTS)
    def delete_traffic(self, rep, **kwargs):
        test = self.test
        traffic = test.traffic
        traffic_to_list = test.traffic_to_list
        assert traffic.keys() == traffic_to_list.keys()
        traffic_id = kwargs['trafficID']
        if traffic_id == 'all':
            ids = traffic.keys()
            ids.sort()
            for id in ids:
                self._delete_traffic(id)
            traffic.clear()
            traffic.clear()
            rest = {'result':'success',
                    'detail':'all traffic deleted'}
            return Response(status=400, body=str(rest) + '\n')
        else:
            traffic_to_delet = traffic_id
            if traffic_id not in traffic.keys():
                rest = {'result':'failure',
                        'detail':'no such traffic'}
                return Response(status=400, body=str(rest) + '\n')
            else:
                self._delete_traffic(traffic_to_delet)
                del traffic[traffic_to_delet]
                del traffic_to_list[traffic_to_delet]
                rest ={'result':'success',
                       'detail':'traffic %s deletetd' % traffic_to_delet}
                return Response(status=400, body=str(rest) + '\n')

    def _delete_traffic(self, traffic_id):
        test = self.test
        traffic = test.traffic[traffic_id]
        match_record = traffic['match']
        for i in match_record.keys():
            dp =test.sw.dps[i]
            match = match_record[i]

             # match._fields2
            new_match = dp.ofproto_parser.OFPMatch()
            new_match._fields2 = match._fields2
            test.remove_flow(dp, new_match)



    #curl -X GET -d "{'src_switch':1, 'mid_switch':5,'dst_switch':3}"  http://localhost:8080/path/get
    @route('test', path_url_base+'/get', methods=['GET'], requirements=None)
    def path_calc(self, req, **kwargs):
        rest = eval(req.body)
        src_switch = rest[REST_SRC_SWITCH]
        dst_switch = rest[REST_DST_SWITCH]
        if REST_MID_SWITCH not in rest:
            path = self.get_path(src_switch, dst_switch)
        else:
            mid_switch = rest[REST_MID_SWITCH]
            path1 = self.get_path(src_switch, mid_switch)
            path2 = self.get_path(mid_switch, dst_switch)
            path = path1 + path2[1:]
        message = 'The path is '
        for i in path:
            message = message+ str(i) + '-->'
        message = message[:-3]
        return Response(status=400, body=message+ '\n')


    def get_path(self, src, dst):
        test = self.test
        topo = get_topo(test)
        path = nx.shortest_path(topo, src, dst)

        return path

    # curl -X PUT -d "{'00:00:00:00:00:03':1,}" http://localhost:8080/mac/add/0000000000000003
    @route('test', mac_url_base + '/add/{switchid}', methods=['PUT'],requirements=REQUIREMENTS)
    def add_mac_to_port(self, req, **kwargs):
        test = self.test
        mac_to_port = test.mac_to_port
        switchid = int(kwargs['switchid'], 16)
        mac_dict = mac_to_port.setdefault(switchid, {})
        rest = eval(req.body)
        for mac, no in rest.items():
            if mac not in mac_dict.keys():
                mac_dict[mac] = no

        return Response(status=400, body='Success!\n')
    ##curl -X GET http://0.0.0.0:8080/mac/list/all
    @route('test', mac_url_base + '/list/{switchid}', methods=['GET'],requirements=REQUIREMENTS)
    def list_mac_to_port(self, req, **kwargs):
        test = self.test
        mac_to_port = test.mac_to_port
        if  not len(mac_to_port) > 0:
            return  Response(status=400, body='No info to dispaly!\n')

        switchesid = kwargs['switchid']
        string = ''
        if switchesid == 'all':
            for i in mac_to_port.keys():
                idinfo = 'switchid: %d ' % i
                portinfo = str(mac_to_port[i])
                string += idinfo + portinfo + '\n'
        else:
            id = int(switchesid, 16)
            portinfo = str(mac_to_port[i])
            string = idinfo + portinfo + '\n'

        return Response(status=400, body=string)
    #curl -X GET http://0.0.0.0:8080/device/list/all
    @route('test', device_url_base+'/list/{switchid}', methods=['GET'], requirements=REQUIREMENTS)
    def list_device_info(self, req, **kwargs):
        test = self.test
        switchid =kwargs['switchid']
        message = ''
        if switchid == 'all':
            for id in test.device_info:
                device_info = test.device_info[id]
                message = message + device_info['name'] + ":"+str(device_info) + '\n'

        else:
            id = int(switchid, 16)
            if id in test.device_info:
                device_info = test.device_info[id]
                message = message + device_info['name'] + ":"+str(device_info) + '\n'
            else:
                message  = message + 'NO SUCH DEVICE!!!\n'

        return Response(status=400, body = str(message))
    #curl -X GET http://0.0.0.0:8080/device/link
    @route('test', device_url_base+'/link', methods=['GET'], requirements=REQUIREMENTS)
    def list_link_info(self, req, **kwargs):
        test = self.test
        message = list_link_status(test)

        return Response(status=400, body = str(message)+ '\n')

    @route('test', '/config/set/{switchid}/ovsdb', methods=['PUT'],requirements={'switchid':dpid_lib.DPID_PATTERN})
    def set_key(self, req, **_kwargs):
        dpid = None
        if 'switchid' in _kwargs:
            dpid = dpid_lib.str_to_dpid(_kwargs['switchid'])

        key = OVSDB_ADDR

        conf_switch = self.test.config
        def _set_val(dpid, key):
            val = json.loads(req.body)
            conf_switch.set_key(dpid, key, val)
            return None

        def _ret(_ret):
            return Response(status=httplib.CREATED)

        return self._do_key(dpid, key, _set_val, _ret)
    @route('test', '/config/get/{switchid}/ovsdb', methods=['GET'],requirements={'switchid':dpid_lib.DPID_PATTERN})
    def get_key(self, _req, **_kwargs):
        dpid = None
        if 'switchid' in _kwargs:
            dpid = dpid_lib.str_to_dpid(_kwargs['switchid'])

        key = OVSDB_ADDR
        conf_switch = self.test.config
        def _get_key(dpid, key):
            return conf_switch.get_key(dpid, key)

        def _ret(val):
            return Response(content_type='application/json',
                            body=json.dumps(val))
        return self._do_key(dpid, key, _get_key, _ret)

    @route('test', '/config/del/{switchid}/ovsdb', methods=['DELETE'],requirements={'switchid':dpid_lib.DPID_PATTERN})
    def delete_key(self, _req,  **_kwargs):

        dpid = None
        if 'switchid' in _kwargs:
            dpid = dpid_lib.str_to_dpid(_kwargs['switchid'])

        conf_switch = self.test.config
        key = OVSDB_ADDR
        def _delete_key(dpid, key):
            conf_switch.del_key(dpid, key)
            return None

        def _ret(_ret):
            return Response()

        return self._do_key(dpid, key, _delete_key, _ret)

    @staticmethod
    def _do_key(dpid, key, func, ret_func):
        ##dpid = dpid_lib.str_to_dpid(dpid)
        try:
            ret = func(dpid, key)
        except KeyError:
            return Response(status=httplib.NOT_FOUND,
                            body='no dpid/key is found %s %s\n' %
                            (dpid_lib.dpid_to_str(dpid), key))
        return ret_func(ret)

    def get_queue_id(self,dpid, bandth):
        test = self.test
        queue_info = get_queue_info(test)
        if dpid not in queue_info:
            print 'eerr'
            return -1
        config = queue_info[dpid]

        for i in config:
            max = int(config[i]['config']['max-rate'])
            min = int(config[i]['config']['min-rate'])
            if bandth <= max and bandth > min:
                return i

        return 0



def label_distribute(switch_list):
    length = len(switch_list)
    label_dict = {}

    l = []
    for i in range(1,10000):
        l.append(i)

    labels = random.sample(l, len(switch_list) - 1)

    for i in range(0, length):
        switch = switch_list[i]
        switch_label = label_dict.setdefault(switch, {})
        if i == 0:
            switch_label['push'] = labels[i]
        elif i == length-1:
            switch_label['pop'] = labels[i - 1]
        else:
            switch_label['push'], switch_label['pop'] = labels[i], labels[i-1]

    return label_dict

