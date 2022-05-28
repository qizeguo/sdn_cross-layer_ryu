__author__ = 'root'

import networkx as nx
import json
import logging
import time
import os
import copy

from ryu.app.net import Task
from ryu.app.topo import TopoInfo
from ryu.app.labelsManager import MplsLabelsPool
from ryu.app.taskManager import TaskPool
from ryu.app.domainInfo import DomainInfo, SwitchInfo

from webob import Response
from ryu.app.wsgi import ControllerBase, WSGIApplication
from ryu.app.wsgi import route
from ryu.base import app_manager
from ryu.app.net import TASK_DICT, delTask, REQ_LIST, assertTaskInDict, getTask, registerTask

from ryu.app.super_reply_controller import SuperReplyController
from ryu.lib import hub

from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.services.protocols.bgp.bgpspeaker import bgpevent

SUPERCONTROLLER = 'SuperController'
SUPERREPLYCONTROLLER = 'SuperReplyController'

SUPERBASEURL = '/super'
DOMAINURLNORETURN = '/domain/noreturn'
DOMAINURLRETURN = '/domain/return'


DOMAINID = 'domainId'
TYPE = 'type'
PATHTYPE = 'pathType'
TASK_ID = 'taskId'
SRC_IP = 'srcIp'
DST_IP = 'dstIp'
SRC_SWITCH = 'srcSwitch'
DST_SWITCH = 'dstSwitch'
BANDWIDTH = 'bandwidth'
PARTPATH = 'path'
LABELS = 'labels'
DOMAINWSGIIP = 'domainWsgiIp'
DOMAINWSGIPORT = 'domainWsgiPort'
NEXT_MAC = 'next_mac'
LOCAL_MAC = 'local_mac'
LAST_OUTPORT_NUM = 'last_outport_num'



class SuperController(app_manager.RyuApp):

    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SuperController, self).__init__(*args, **kwargs)

        self.wsgiIp = None
        self.wsgiPort = None
        ##################################################
        self.topo = TopoInfo()
        self.trafficBalance = True
        ##################################################
        self.LabelsPool = MplsLabelsPool()
        self.LabelsPool.initPool()
        ##################################################
        self.domains = {}

        ###################################################
        self.table = Table

        wsgi = kwargs['wsgi']
        data = {}
        data[SUPERCONTROLLER] = self
        data[SUPERREPLYCONTROLLER] = SuperReplyController()
        wsgi.register(SuperWsgiController, data)
        # self.newtaskThreadFlag = self.CONF.newtask_thread_flag
        # if self.newtaskThreadFlag:
        # self.newtaskThread = hub.spawn(self.newTask)


    def startBackupHandler(self, taskId):
        taskInstance = getTask(taskId)
        backupPathDomains = taskInstance.getBackupCrossDomains()
        if not backupPathDomains:
            self.logger.info('NO Backup Path for this Task')
            return

        mainPathDomains = taskInstance.getMainCrossDomains()

        handlerDomains = self._add_diff_from_list(backupPathDomains, mainPathDomains)

        for domainId in handlerDomains:
            self.sendStartBackupPathMsg(domainId, taskId)

        taskInstance.changeBackupToMain()

    def _add_diff_from_list(self, list1, list2):
        list_ = []
        for i in list1:
            list_.append(i)

        for j in list2:
            if j not in list_:
                list_.append(j)

        return list_

    def sendStartBackupPathMsg(self, domainId, taskId):
        send_message = self._make_start_backup_msg(domainId, taskId)
        command = self._to_commad(send_message)
        print "start backup: ", command
        self.send_no_return_command(command)

    def _make_start_backup_msg(self, domainId, taskId):

        to_send = {}
        to_send[TYPE] = 'startBackup'
        to_send[DOMAINID] = domainId
        to_send[TASK_ID] = taskId

        send_message = json.dumps(to_send)
        return send_message

    def setNewBackupPath(self, taskId):
        taskInstance = getTask(taskId)
        completePathMain = taskInstance.getMainCompletePath()
        assert len(completePathMain) > 1  # to make sure we set a backupPath for a task having a mainPath
        mainEdges = taskInstance.getMainEdges()
        newTopo = self.topo.getNewTopoExceptSE(mainEdges)

        srcSwitch = taskInstance.getSrcSwtich()
        dstSwtich = taskInstance.getDstSwitch()

        if self.trafficBalance:
            newCompletePathBackup = newTopo.getWeightPath(srcSwitch, dstSwtich)
        else:
            newCompletePathBackup = newTopo.getShortestPath(srcSwitch, dstSwtich)

        if not newCompletePathBackup:
            self.logger.warning("can not assign a new backupPath for this task ")
            return

        taskInstance.setBackupCompletePath(newCompletePathBackup)
        nodeToDomain = self.topo.nodeToDomainId
        newBackupSectorialPath = taskInstance.getBackupSectorialPath(nodeToDomain)

        newAllBackupPathMpls = self.LabelsPool.getLabels(len(newCompletePathBackup))
        noUseLabels = taskInstance.assignBackuPathMpls(newAllBackupPathMpls)
        self.LabelsPool.recycleLabels(noUseLabels)

        for i in newBackupSectorialPath:
            send_message = taskInstance.makeDoaminTaskAssign(i,  type='backup')
            command = self._to_commad(send_message)
            print 'newbackup: ', command
            self.send_no_return_command(command)
            taskInstance.addBackupUnconfirmDomain(i)


    def _keep_alive(self):
        while True:
            for i in self.domains:
                self.sendKeepAlive(i)
                self.logger.info("send keepalive to domain %d" % i)
            hub.sleep(10)

    def sendKeepAlive(self, i):
        send_message = self._make_keep_alive(i)
        command = self._to_commad(send_message)
        self.send_no_return_command(command)


    def _make_keep_alive(self, i):
        to_send = {}
        to_send[TYPE] = 'keepAlive'
        to_send[DOMAINID] = i

        send_message = json.dumps(to_send)
        return send_message


    def send_no_return_command(self, command):
        try:
            os.popen2(command)
        except:
            self.logger.debug('command exceute fail.Fail Command: %s' % command)
            return

    def _to_commad(self, send_message, returnType=False):

        message = eval(send_message)
        domainId = message.get(DOMAINID)
        domainInstance = self.domains.get(domainId)
        domainWsgiIp = domainInstance.getWsgiIp()
        domainWsgiPort = domainInstance.getWsgiPort()

        command = 'curl -X '
        if returnType:
            command += 'GET -d \''
        else:
            command += 'PUT -d \''
        command += send_message
        command += '\' http://'
        command += domainWsgiIp
        command += ':'
        command += str(domainWsgiPort)
        if not returnType:
            command += DOMAINURLNORETURN
        else:
            command += DOMAINURLRETURN

        command += ' 2> /dev/null'

        return command

    ###################################################################



    @set_ev_cls(bgpevent, MAIN_DISPATCHER)
    def handler_bgp_msg(self, ev):
        bgp_msg = ev.ev
        remote_as = bgp_msg.remote_as
        route_dist = bgp_msg.route_dist
        prefix = bgp_msg.prefix
        nexthop = bgp_msg.nexthop
        label = bgp_msg.label
        is_withdraw = bgp_msg.is_withdraw
        Table.prefix_to_nexthop = {prefix: nexthop}


class SuperWsgiController(ControllerBase):

    def __init__(self, req, link, data, **config):
        super(SuperWsgiController, self).__init__(req, link, data, **config)
        self.name = 'SuperWsgiController'
        self.SuperController = data[SUPERCONTROLLER]
        self.SuperReplyController = data[SUPERREPLYCONTROLLER]
        # self.newtaskThread = hub.spawn(self.newTask)


        if hasattr(self.__class__, 'LOGGER_NAME'):
            self.logger = logging.getLogger(self.__class__.LOGGER_NAME)
        else:
            self.logger = logging.getLogger(self.name)

    @route('super', SUPERBASEURL + '/noreturn', methods=['PUT'], requirements=None)
    def noreturned_command_handler(self, req):
        msgbody = eval(req.body)
        assert TYPE in msgbody
        type = msgbody.get(TYPE, None)
        if not type:
            self.logger.fatal("Not type in msgbody")
            return

        try:
            func = getattr(self.SuperReplyController, type)
            if type is 'ArpMessage':
                func(msgbody, self.SuperController, Table)
        except:
            self.logger.fatal('can not find handler')
            return

        func(msgbody, self.SuperController)

    @route('super', SUPERBASEURL + '/return', methods=['PUT'], requirements=None)
    def returned_command_handler(self, req):
        msgbody = eval(req.body)
        assert TYPE in msgbody
        type = msgbody.get(TYPE, None)
        if not type:
            self.logger.fatal("Not type in msgbody")
            return

        try:
            func = getattr(self.super_reply_controller, type)
        except:
            self.logger.error('Can not find handler')
            return

        func(msgbody, self.SuperController)


    # @route('super', SUPERBASEURL + '/task/assign', methods=['PUT'], requirements=None)

    @route('super', SUPERBASEURL + '/newtask', methods=None, requirements=None)
    def newTask(self):

        taskpoolinstance = TaskPool()
        Peer_Table = {('10.108.90.1', '10.108.91.0/24'): Table.return_src_and_dst_dpid('10.108.90.1', '10.108.91.0/24'),
                      ('10.108.91.1', '10.108.90.0/24'): Table.return_src_and_dst_dpid('10.108.91.1', '10.108.90.0/24')}

        SC = self.SuperController
        peer_table = copy.copy(Peer_Table)
        #self.sleep = 120
        #hub.sleep(self.sleep)

        for s_d in peer_table.keys():
            if s_d:
                req = {SRC_SWITCH: peer_table[s_d][0],
                       DST_SWITCH: peer_table[s_d][2],
                       LAST_OUTPORT_NUM: peer_table[s_d][3],
                       SRC_IP: s_d[0], DST_IP: s_d[1],
                       LOCAL_MAC: peer_table[s_d][4],
                       NEXT_MAC: peer_table[s_d][5],
                       BANDWIDTH: {"peak": 50000000, "guranted": 20000000},
                       TASK_ID: taskpoolinstance.get_taskid()}
                REQ_LIST.append(req)

                SC.taskAssign(self, req)
                self.logger.info("Build a path from %0x16 to %0x16" % (SRC_SWITCH, DST_SWITCH))



    def taskAssign(self, req):

        SC = self.SuperController
        body = req.body
        rest = eval(body)
        taskId = rest[TASK_ID]

        if not taskId:
            return Response(status=200, body="Input a task Id\n")
        if assertTaskInDict(taskId):
            taskInstance = getTask(taskId)
        else:
            taskInstance = Task(taskId)

        if taskInstance.isEstablished():

            return Response(status=200, body="taskId duplicated!\n")

        srcSwitch = rest[SRC_SWITCH]
        dstSwitch = rest[DST_SWITCH]
        bandwith = rest[BANDWIDTH]
        # duration = rest[]
        dstIp = rest[DST_IP]
        srcIp = rest[SRC_IP]
        local_mac = rest[LOCAL_MAC]
        next_mac = rest[NEXT_MAC]
        last_outport_num = rest[LAST_OUTPORT_NUM]
        taskInstance.taskSetFields(srcSwitch=srcSwitch, dstSwitch=dstSwitch, srcIp=srcIp, dstIp=dstIp, local_mac=local_mac, next_mac=next_mac, last_outport_num=last_outport_num, bandwidth=bandwith)


        if SC.trafficBalance:
            completePathMain = SC.topo.getWeightPath(srcSwitch, dstSwitch)
            if not completePathMain:
                self.logger.warning("no main path between switch %d and %d" % (srcSwitch, dstSwitch))
                return Response(status=200, body="no main path between switch %d and %d\n" % (srcSwitch, dstSwitch))

            taskInstance.setMainCompletePath(completePathMain)
            mainEdges = taskInstance.getMainEdges()
            newTopo = SC.topo.getNewTopoExceptSE(mainEdges)
            completePathBackup = newTopo.getWeightPath(srcSwitch, dstSwitch)
            if not completePathBackup:
                self.logger.warning("no backup path between switch %d and %d" % (srcSwitch, dstSwitch))

            taskInstance.setBackupCompletePath(completePathBackup)
        else:
            completePathMath = SC.topo.getShortestPath(srcSwitch, dstSwitch)
            if not completePathMath:
                self.logger.warning("no main path between switch %d and %d" % (srcSwitch, dstSwitch))
                return Response(status=200, body="no main path between switch %d and %d\n" % (srcSwitch, dstSwitch))

            taskInstance.setMainCompletePath(completePathMath)
            mainEdges = taskInstance.getMainEdges()
            newTopo = SC.topo.getNewTopoExceptSE(mainEdges)
            completePathBackup = newTopo.getShorestPath(srcSwitch, dstSwitch)
            if not completePathBackup:
                self.logger.warning("no backup path between switch %d and %d" % (srcSwitch, dstSwitch))

            taskInstance.setBackupCompletePath(completePathBackup)

        nodeToDomian = SC.topo.nodeToDomainId
        mainSectorialPath = taskInstance.getMainSectorialPath(nodeToDomian)
        backupSectorialPath = taskInstance.getBackupSectorialPath(nodeToDomian)
        # print mainSectorialPath
        # print backupSectorialPath


        allMainPathMpls = SC.LabelsPool.getLabels(len(completePathMain))
        noUseLabels = taskInstance.assignMainPathMpls(allMainPathMpls)
        SC.LabelsPool.recycleLabels(noUseLabels)

        allBackupPathMpls = SC.LabelsPool.getLabels(len(completePathBackup))
        noUseLabels = taskInstance.assignBackuPathMpls(allBackupPathMpls)
        SC.LabelsPool.recycleLabels(noUseLabels)

        registerTask(taskInstance)
        # print "main: ", completePathMain
        # print "backup: ", completePathBackup
        # print "nodeToDomain: ", nodeToDomian

        for i in mainSectorialPath:
            send_message = taskInstance.makeDoaminTaskAssign(i)

            command = SC._to_commad(send_message)
            print "main: ", command
            SC.send_no_return_command(command)
            taskInstance.addMainUnconfirmDomain(i)

        

        for j in backupSectorialPath:
            send_message = taskInstance.makeDoaminTaskAssign(j, type='backup')

            command = SC._to_commad(send_message)
            print "backup: ",command
            SC.send_no_return_command(command)
            taskInstance.addBackupUnconfirmDomain(j)


    @route('super', SUPERBASEURL + '/task/delete', methods=['PUT'], requirements=None)
    def taskDelete(self, req):

        SC = self.SuperController
        rest = eval(req)

        taskId = rest[TASK_ID]
        if not assertTaskInDict(taskId):
            self.logger.info("no task %d" % taskId)
            return Response(status=200, body='No task %d\n' % taskId)

        taskInstance = getTask(taskId)
        allCrossDomains = taskInstance.getAllDomains()
        taskInstance.setDeleteDomains(allCrossDomains)
        for i in allCrossDomains:
            send_message = taskInstance.makeTaskDeleteMsg(i)
            command =SC._to_commad(send_message)
            SC.send_no_return_command(command)


class table(object):

    _instance = None


    @staticmethod
    def get_instance():
        if not table._instance:
            table._instance = table()
        return table._instance

    def __init__(self):

        self.ip_to_mac = {}
        self.ip_to_port = {}
        self.port_to_dpid = {}
        self.prefix_to_nexthop = {}
        self.dpid_to_mac = {  '0000000000000201'  : '48:6e:73:02:03:07',  '0000000000000202' : '48:6e:73:02:03:07',
         '0000000000000203' : '48:6e:73:02:03:07',  '0000000000000204' : '48:6e:73:02:03:07', 
         '0000000000000205' : '48:6e:73:02:03:07', '0000000000000206' : '48:6e:73:02:03:07', 
         '0000000000000301' : '48:6e:73:02:03:10', '0000000000000302' : '48:6e:73:02:03:10', 
         '0000000000000303' : '48:6e:73:02:03:10', '0000000000000304' : '48:6e:73:02:03:10', 
         '0000000000000305' : '48:6e:73:02:03:10', '0000000000000306' : '48:6e:73:02:03:10'}

    def return_src_and_dst_dpid(self, prefix, src_ip):#src_ip is a ip address,prefix is a ip address with mask
        nexthop = self.prefix_to_nexthop.get(prefix, None)
        src_dpid,dst_dpid = self.get_src_and_dst_dpid(src_ip, nexthop)
        src_port = self.ip_to_port[src_ip]
        dst_port = self.ip_to_port[nexthop]
        dst_dpid_mac = self.dpid_to_mac[dst_dpid]
        next_mac = self.ip_to_mac[nexthop]
        return (src_dpid, src_port,dst_dpid, dst_port,dst_dpid_mac,next_mac)

    def get_src_and_dst_dpid(self, src_ip, next_hop):
        src_port = self.ip_to_port.get(src_ip, None)
        dst_port = self.ip_to_port.get(next_hop, None)
        a = 0
        if src_port is None or dst_port is None:
            a = 1

        if a == 0:
            src_dpid = self.port_to_dpid.get(src_port, None)
            dst_dpid = self.port_to_dpid.get(dst_port, None)
            return src_dpid, dst_dpid
        else:
            print "there is no correspondent ports on the switches."

Table = table.get_instance()







