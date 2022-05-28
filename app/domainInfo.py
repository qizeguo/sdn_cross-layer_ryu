__author__ = 'Johnny'


import time

class DomainInfo(object):

    def __init__(self, domainId, *args, **kwargs):

        self.doaminId = domainId
        self.enterTime = time.time()
        self.switches = []
        self.switchesFeatures = {}
        self.linkPort = []
        self.wsgiIp = None
        self.wsgiPort = None

        self.enterTime = time.time()
        self.lastEchoTime = None

    def setWsgiIp(self, ip):
        self.wsgiIp = ip

    def getWsgiIp(self):
        return self.wsgiIp

    def setWsgiPort(self, port):
        self.wsgiPort = port

    def getWsgiPort(self):
        return self.wsgiPort

    def setLastEchoTime(self, time):
        self.lastEchoTime = time

    def getLastEchoTime(self, time):
        return self.lastEchoTime

    def setDomainFields(self, ip, port, time):
        self.setWsgiIp(ip)
        self.setWsgiPort(port)
        self.setLastEchoTime(time)

    def addSwitch(self, node):
        if node not in self.switches:
            self.switches.append(node)

    def removeSwitch(self, node):
        if node in self.switches:
            self.switches.remove(node)

        if node in self.switchesFeatures:
            del self.switchesFeatures[node]

    def isEmpty(self):
        return self.switches is None

    def addLink(self, src, srcPort, dst, dstPort):
        item = (src, srcPort, dst, dstPort)
        if item not in self.linkPort:
            self.linkPort.append(item)

    def deleteLink(self, src, srcPort, dst, dstPort):
        item = (src, srcPort, dst, dstPort)
        if item in self.linkPort:
            self.linkPort.remove(item)

    def getSwtchFeature(self, node):
        assert node in self.switchesFeatures
        return self.switchesFeatures[node]

    def addSwtichFeature(self, node, features):

        assert isinstance(features, SwitchInfo)
        if node not in self.switchesFeatures:
            self.switchesFeatures[node] = features

        else:
            tempFeatures = self.switchesFeatures.get(node)
            createTime = tempFeatures.getCreatTime()
            if createTime < time.time():
                self.switchesFeatures[node] = features

    def isSwitchIn(self, node):
        return node in self.switches

    def isLinkPortIn(self, item):
        return item in self.linkPort

    def checkAlive(self):
        if self.switches or self.linkPort or self.switchesFeatures:
            return True
        else:
            return False


class SwitchInfo(object):

    def __init__(self, dpid, *args, **kwargs):

        self.dpid = dpid
        self.name = None
        self.creatTime = time.time()
        # self.version = None
        # self.capablities = None
        # self.n_buffers = None
        # self.n_tables = None
        # self.auxiliary_id = None
        self.ports ={}


    def getCreatTime(self):
        return self.creatTime

    def setName(self, name):
        self.name = name

    def getPorts(self):
        return self.ports

    def getPort(self, portNo):
        port = str(portNo)
        assert port in self.ports
        return self.ports[port]

    def getDpid(self):
        return self.dpid

    def getCurrSpeed(self, portNo):
        assert portNo in self.ports
        port = self.ports[portNo]
        return port.getCurrSpeed()

class PortInfo(object):
    def __init__(self, portNo, *args, **kwargs):

        self.portNo = portNo
        self.name = None
        self.hw_addr = None
        self.config = None
        self.curr = None
        self.max_speed = None
        self.curr_speed = None

        self.lastCollect = 0
        self.lastTime = 0

    def setFieldsfromDict(self, infoDict):
        assert isinstance(infoDict, dict)

        if 'name' in infoDict:
            self.name = infoDict['name']

        if 'hw_addr' in infoDict:
            self.hw_addr = infoDict['hw_addr']

        if 'config' in infoDict:
            self.config = infoDict['config']

        if 'curr' in infoDict:
            self.curr = infoDict['curr']

        if 'max_speed' in infoDict:
            self.max_speed = infoDict['max_speed']

        if 'curr_speed' in infoDict:
            self.curr_speed = infoDict['curr_speed']


    def getCurrSpeed(self):
        return self.curr_speed

    def getLastCollect(self):
        return self.lastCollect

    def getLastTime(self):
        return self.lastTime

    def updateLasttime(self, times):
        self.lastTime = times

