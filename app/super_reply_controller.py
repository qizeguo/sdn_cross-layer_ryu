__author__ = 'root'

import logging
import time
from ryu.app.domainInfo import DomainInfo, SwitchInfo, PortInfo
from ryu.app.net import TASK_DICT, getTask, getBackupPathEffect, getMainPathEffect, assertTaskInDict, Task, delTask

DOMAINID = 'domainId'
DPID = 'dpid'
TYPE = 'type'
PATHTYPE = 'pathType'
TASK_ID = 'taskId'
SRC_IP = 'srcIp'
DST_IP = 'dstIp'
SRC_SWITCH = 'srcSwitch'
DST_SWITCH = 'dstSwitch'
SRC_PORT = 'srcPort'
DST_PORT = 'dstPort'

PORTSTATS = 'ports'

DOMAINWSGIIP = 'domainWsgiIp'
DOMAINWSGIPORT = 'domainWsgiPort'

SWITCHFEATURE = 'features'

class SuperReplyController(object):

    def __init__(self):
        self.name = 'SuperReplyController'
        if hasattr(self.__class__, 'LOGGER_NAME'):
            self.logger = logging.getLogger(self.__class__.LOGGER_NAME)
        else:
            self.logger = logging.getLogger(self.name)
        self.logger.info("I am Super Reply Controller!")


    def switchEnter(self, jsonMsg, SC):

        assert jsonMsg[TYPE] == 'switchEnter'
        domainId = jsonMsg.get(DOMAINID)
        domainInstance = SC.domains.setdefault(domainId, DomainInfo(domainId))
        node = jsonMsg[DPID]
        domainInstance.addSwitch(node)
        topo = SC.topo
        topo.addNode(node, domainId)

        self.logger.info("Switch %016x enter in global topo" % node)


    def switchLeave(self, jsonMsg, SC):

        assert jsonMsg[TYPE] == 'switchLeave'
        domainId = jsonMsg.get(DOMAINID)
        domainInstance = SC.domains.get(domainId, None)
        if not domainInstance:
            self.logger.warning("Switch leave from no_exist domain. DomianId: %d" % domainId)
            return

        node = jsonMsg[DPID]
        if domainInstance.isSwitchIn(node):
            domainInstance.removeSwitch(node)
            self.logger.info("Switch %16x leave from global topo" % node)

        topo = SC.topo
        if topo.isNodeIn(node):
            topo.removeNode(node, domainId)
            self.logger.info("Switch %16x leave from global topo" % node)

        if not domainInstance.checkAlive():
            del SC.domains[domainId]
            self.logger.info("Domain %d Leave" % domainId)


    def linkAdd(self, jsonMsg, SC):
        assert jsonMsg[TYPE] == 'linkAdd'

        domainId = jsonMsg[DOMAINID]
        domainInstance = SC.domains.setdefault(domainId, DomainInfo(domainId))
        srcSwitch = jsonMsg[SRC_SWITCH]
        dstSwitch = jsonMsg[DST_SWITCH]
        srcPort = jsonMsg[SRC_PORT]
        dstPort = jsonMsg[DST_PORT]

        item = (srcSwitch, srcPort, dstSwitch, dstPort)
        if not domainInstance.isLinkPortIn(item):
            domainInstance.addLink(srcSwitch, srcPort, dstSwitch, dstPort)

        topo = SC.topo

        if (srcSwitch, dstSwitch) not in topo.edges():
            topo.addEdge(srcSwitch, srcPort, dstSwitch, dstPort)
            self.logger.info("Global topo link add:src %16x port_no %8d-> dst %16x %8d" % (srcSwitch, srcPort,
                                                                                           dstSwitch, dstPort))


    def linkDelete(self, jsonMsg, SC):
        assert jsonMsg[TYPE] == 'linkDelete'
        domainId = jsonMsg[DOMAINID]
        domainInstance = SC.domains.get(domainId, None)
        if not domainInstance:
            self.logger.warning("Link delete from no-exist domain. Domain: %d", domainId)
            return

        srcSwitch = jsonMsg[SRC_SWITCH]
        dstSwitch = jsonMsg[DST_SWITCH]
        srcPort = jsonMsg[SRC_PORT]
        dstPort = jsonMsg[DST_PORT]

        item = (srcSwitch, srcPort, dstSwitch, dstPort)

        if domainInstance.isLinkPortIn(item):
            domainInstance.deleteLink(srcSwitch, srcPort, dstSwitch, dstPort)
        topo = SC.topo
        if (srcSwitch, dstSwitch) in topo.edges():
            topo.removeEdge(srcSwitch, srcPort, dstSwitch, dstPort)
            self.logger.info("Global topo link delete:src %16x port_no %8d-> dst %16x %8d" % (srcSwitch, srcPort,
                                                                                              dstSwitch, dstPort))
        print TASK_DICT
        linkDeleted = (srcSwitch, dstSwitch)
        mainPathEffect = getMainPathEffect(linkDeleted)
        for taskId in mainPathEffect:
            SC.startBackupHandler(taskId)
        backupPathEffect = getBackupPathEffect(linkDeleted)
        for i in mainPathEffect:
            if i not in backupPathEffect:
                backupPathEffect.append(i)

        for taskId in backupPathEffect:
            # SC.setNewBackupPath(taskId)
            pass




    def portStats(self, jsonMsg, SC):
        assert jsonMsg[TYPE] == 'portStats'
        domainId = jsonMsg[DOMAINID]
        assert domainId in SC.domains

        domainInstance = SC.domains[domainId]

        dpid = jsonMsg[DPID]
        ports = jsonMsg[PORTSTATS]

        edges = []
        topo = SC.topo
        for i in ports:
            portNo = int(i)
            edge = topo.getEdgeFromDstPoint(dpid, portNo)
            if edge:
                switchFeature = domainInstance.getSwtchFeature(dpid)
                portInfo = switchFeature.getPort(portNo)
                BaseSpeed = portInfo.getCurrSpeed()
                lastTime = portInfo.getLastTime()
                timeNow = time.time()
                gapTime = timeNow - lastTime
                cur = ports[i]
                weight = self._get_weight(BaseSpeed, cur, gapTime)
                edges.append((edge[0], edge[1], {'weight':weight}))

        topo.updateWeight(edges)


    def _get_weight(self, base, cur, gaptime):
        minCur = float(cur) / gaptime
        weight = float(base) / (base - minCur)
        return weight


    def switchFeature(self, jsonMsg, SC):
        assert jsonMsg[TYPE] == 'switchFeature'
        domainId = jsonMsg[DOMAINID]

        domainInstance = SC.domains.setdefault(domainId, DomainInfo(domainId))
         # domain object
        dpid = jsonMsg[DPID]

        if not domainInstance.isSwitchIn(dpid):
            domainInstance.addSwitch(dpid)

        switchFeaturs = SwitchInfo(dpid)     #switch object
        features = jsonMsg[SWITCHFEATURE]
        name = features['name']
        switchFeaturs.setName(name)

        ports = switchFeaturs.getPorts()

        portsInfo = features['ports']
        for portNo in portsInfo:
            assert portNo in portsInfo
            portInfo = portsInfo[portNo]
            port = PortInfo(portNo)
            port.setFieldsfromDict(portInfo)

            if portNo not in ports:
               ports[portNo] = port

        domainInstance.addSwtichFeature(dpid, switchFeaturs)

    def keepAlive(self, jsonMsg, SC):
        assert jsonMsg[TYPE] == 'keepAlive'

        domainId = jsonMsg[DOMAINID]
        domainInstance = SC.domains.setdefault(domainId, DomainInfo(domainId))
        domainWsgiIp = jsonMsg[DOMAINWSGIIP]
        domainWsgiPort = jsonMsg[DOMAINWSGIPORT]
        lastEchoTime = time.time()

        domainInstance.setDomainFields(domainWsgiIp, domainWsgiPort, lastEchoTime)

    def taskAssignReply(self, jsonMsg, SC):
        assert jsonMsg[TYPE] == 'taskAssignReply'

        taskId = jsonMsg[TASK_ID]
        try:
            taskInstance = getTask(taskId)
        except:
            self.logger.warning("receive a task assign reply to a task not assign")
            return

        domainId = jsonMsg[DOMAINID]
        pathType = jsonMsg[PATHTYPE]

        if pathType == 'main':
            print 'receive main reply'
            taskInstance.removeMainUnconfirmDomain(domainId)
        if pathType == 'backup':
            print 'receive backup reply'
            taskInstance.removeBackupUnconfirmDomain(domainId)

        if taskInstance.checkTaskStatus():
            self.logger.info("Task %d Established" % taskId)

    #####  dai xiugai
    def taskDeleteReply(self, jsonMsg, SC):

        assert jsonMsg[TYPE] == 'taskDeleteReply'

        taskId = jsonMsg[TASK_ID]

        if not assertTaskInDict(taskId):
            self.logger.info("No such task")
            return

        taskInstance = getTask(taskId)
        # taskInstance = Task(1)

        domainId = jsonMsg[DOMAINID]

        allDeleteDomians = taskInstance.getDeleteDomains()

        assert domainId in allDeleteDomians

        taskInstance.removeDeleteDomain(domainId)

        if taskInstance.isCheckToDelete():
            allLabels = taskInstance.getAllMpls()
            SC.LabelsPool.recycleLabels(allLabels)

            delTask(taskId)
            self.logger.info("Task %d deleted" % taskId)

    def ArpMessage(self, jsonMsg, SC, Table):
            assert jsonMsg[TYPE] == 'ArpMessage'
            Table.ip_to_port = Table.ip_to_port.update(jsonMsg['ip_to_port'])
            Table.ip_to_mac = Table.ip_to_mac.update(jsonMsg['ip_to_mac'])
            Table.port_to_dpid = Table.port_to_dpid.update(jsonMsg['port_to_dpid'])


