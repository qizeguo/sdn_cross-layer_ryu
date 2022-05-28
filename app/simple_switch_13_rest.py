__author__ = 'root'

import json
import logging

from ryu.app import simple_switch_13
from webob import Response
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.app.wsgi import ControllerBase,WSGIApplication,route
from ryu.lib import dpid as dpid_lib

import os

simple_switch_instance_name = 'simple_switch_api_app'
url = '/simpleswitch/mactable/{dpid}'

class SimpleSwitchRest13(simple_switch_13.SimpleSwitch13):

    _CONTEXTS = {'wsgi':WSGIApplication}

    def __init__(self,*args,**kwargs):
        super(SimpleSwitchRest13,self).__init__(*args,**kwargs)
        self.switches = {}
        self.superWsgiIp = self.CONF.super_wsgi_ip
        self.superWsgiPort = self.CONF.super_wsgi_port
        wsgi = kwargs['wsgi']
        wsgi.register(SimpleSwitchController,{simple_switch_instance_name:self})


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures,CONFIG_DISPATCHER)
    def switch_features_handler(self,ev):
        super(SimpleSwitchRest13,self).switch_features_handler(ev)
        datapath = ev.msg.datapath
        self.switches[datapath.id] = datapath
        self.mac_to_port.setdefault(datapath.id,{})

    def set_mac_to_port(self,dpid,entry):
        mac_table = self.mac_to_port.setdefault(dpid,{})
        datapath = self.switches.get(dpid)

        entry_port = entry['port']
        entry_mac = entry['mac']

        if datapath is not None:
            parser = datapath.ofproto_parser
            if entry_port not in mac_table.values():

                for mac,port in mac_table.items():

                    #from known device to new device
                    actions = [parser.OFPActionOutput(entry_port)]
                    match = parser.OFPMatch(in_port=port,eth_dst=entry_mac)
                    self.add_flow(datapath,1,match,actions)

                    #from new device to known device
                    actions = [parser.OFPActionOutput(port)]
                    match = parser.OFPMatch(in_port=entry_port,eth_dst=mac)
                    self.add_flow(datapath,1,match,actions)

                mac_table.update({entry_mac:entry_port})
        return mac_table

class SimpleSwitchController(ControllerBase):

    def __init__(self,req,link,data,**config):
        super(SimpleSwitchController,self).__init__(req,link,data,**config)
        self.simpl_switch_spp = data[simple_switch_instance_name]

#{'dpid':dpid_lib.DPID_PATTERN}
    @route('simpleswitch',url,methods=['GET'],requirements={'dpid':dpid_lib.DPID_PATTERN})
    def list_mac_table(self,req,**kwargs):

        simple_switch = self.simpl_switch_spp
        dpid = dpid_lib.str_to_dpid1(kwargs['dpid'])
        #print dpid,kwargs['dpid']
        #print 1111111111111111111111
        #mac_to_port
        #{514: {'bc:67:1c:02:8a:04': 8}, 515: {'bc:67:1c:02:8a:04': 14}}
        #dpid = 9120431834591789832
        if dpid not in simple_switch.mac_to_port:
            return Response(status=404)

        mac_table = simple_switch.mac_to_port.get(dpid,{})
        mac_table1 = {}########
        mac_table1[dpid] = mac_table########
        body = json.dumps(mac_table1)########
        return Response(content_type='application/json',body=body)

    @route('simpleswitch',url,methods=['PUT'],requirements={'dpid':dpid_lib.DPID_PATTERN})
    def put_mac_table(self,req,**kwargs):

        simple_switch = self.simpl_switch_spp
        dpid = dpid_lib.str_to_dpid(kwargs['dpid'])
        new_entry = eval(req.body)

        if dpid not in simple_switch.mac_to_port:
            return Response(status=404)

        try:
            mac_table = simple_switch.set_mac_to_port(dpid,new_entry)
            body = json.dumps(mac_table)
            return Response(content_type='application/json',body=body)
        except Exception as e:
            return Response(status=500)


    def _to_commad(self, send_message, returnType=False):

        command = 'curl -X '
        if returnType:
            command += 'GET -d \''
        else:
            command += 'PUT -d \''
        command += send_message
        command += '\' http://'
        command += self.simpl_switch_spp.superWsgiIp
        command += ':'
        command += str(self.simpl_switch_spp.superWsgiPort)
        command += '/super/noreturn'
        command += ' 2> /dev/null'


        return command

    # @staticmethod
    def send_no_return_command(self, command):
        print command
        os.popen2(command)


    @route('simpleswitch','/simpleswitch/mactable/mac_to_port',methods=['GET'],requirements=None)
    def get_mac_to_port(self,req):
        mac_port = self.simpl_switch_spp.mac_to_port
        mac_port['type'] = 'mac_to_port'
        send_msg = json.dumps(mac_port)
        command = self._to_commad(send_msg)
        self.send_no_return_command(command)