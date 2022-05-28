__author__ = 'root'

import time


class DomainTask(object):

    def __init__(self, taskId, name=None):

        self.taskId = taskId
        self.creatTime = time.time()
        if name:
            self.name = name
        else:
            self.name = 'DomainTask ' + time.ctime(time.time())

        self.srcSwitch = None
        self.dstSwitch = None
        self.srcIp = None
        self.dstIp = None

        self.mainPath = False
        self.mainList = {}
        self.mainLabels = []
        self.mainMatchInfo = {}
        self.mainPortToQueueId = {}

        self.backupPath = False
        self.backupList = {}
        self.backupLabesl = []
        self.backupMatchInfo = {}
        self.backupPortToQueueId = {}
        self.backupmod = None

        self.bandwidth = {}

    def changeBackupToMain(self):
        self.mainPath = True
        self.mainList = self.backupList
        self.mainLabels = self.backupLabesl
        self.mainMatchInfo = self.backupMatchInfo

        self._clear_backup()

    def _clear_backup(self):
        self.backupPath = False
        self.backupList = {}
        self.backupLabesl = []
        self.backupMatchInfo = {}
        self.backupmod = None

    def setSrcSwitch(self, srcSwitch):
        self.srcSwitch = srcSwitch

    def getSrcSwitch(self):
        return self.srcSwitch

    def setDstSwitch(self, dstSwtich):
        self.dstSwitch = dstSwtich

    def getDstSwitch(self):
        return self.dstSwitch

    def setSrcIp(self, srcIp):
        self.srcIp = srcIp

    def getSrcIp(self):
        return self.srcIp

    def setDstIp(self, dstIp):
        self.dstIp =dstIp

    def getDstIp(self):
        return self.dstIp

    def setBandwith(self, bandwidth):
        self.bandwidth = bandwidth

    def getBandwidth(self):
        return self.bandwidth

    def getMaxRate(self):
        bandwidth = self.getBandwidth()
        maxRate = bandwidth['peak']
        return maxRate

    def getMinRate(self):
        bandwidth = self.getBandwidth()
        minRate = bandwidth['guranted']
        return minRate

    def setBackupMod(self, mod):
        self.backupmod = mod

    def getBackupMod(self):
        return self.backupmod

    def addMainMatchInfo(self, dpid, match):
        assert dpid not in self.mainMatchInfo
        self.mainMatchInfo[dpid] = match

    def getMainMatchInfo(self, dpid):
        assert dpid in self.mainMatchInfo
        return self.mainMatchInfo[dpid]

    def addBackupMatchInfo(self, dpid, match):
        # assert dpid not in self.backupMatchInfo
        self.backupMatchInfo[dpid] = match

    def getBackupMatchInfo(self, dpid):
        assert dpid in self.backupMatchInfo
        return self.backupMatchInfo[dpid]

    def setFields(self, srcSwitch, dstSwitch, bandwidth,
                  path, labels, pathType):
        if not self.srcSwitch:
            self.setSrcSwitch(srcSwitch)

        if not self.dstSwitch:
            self.setDstSwitch(dstSwitch)

        # if not self.srcIp:
        #     self.setSrcIp(srcIp)
        #
        # if not self.dstIp:
        #     self.setDstIp(dstIp)

        if not self.bandwidth:
            self.setBandwith(bandwidth)

        if pathType == 'main':
            self.mainPath = True
            self.mainList = path
            self.mainLabels = labels
        elif pathType == 'backup':
            self.backupPath = True
            self.backupList = path
            self.backupLabesl = labels

    def getPreSwitch(self, pathType):
        if pathType == 'main':
            assert self.mainPath
            preSwith = self.mainList['pre']
        elif pathType == 'backup':
            assert self.backupPath
            preSwith = self.backupList['pre']

        return preSwith



    def getPostSwitch(self, pathType):
        if pathType == 'main':
            assert self.mainPath
            postSwitch = self.mainList['post']
        elif pathType == 'backup':
            assert self.backupPath
            print self.backupList
            postSwitch = self.backupList['post']
        return postSwitch

    def getSwitchList(self, pathType):
        if pathType == 'main':
            switchList = self.mainList['list']
        elif pathType == 'backup':
            switchList = self.backupList['list']
        return switchList

    def getSwithListLength(self, pathType):

        return len(self.getSwitchList(pathType))

    def setMainPortToQueueId(self, switch, portNo, queueId):
        assert switch not in self.MainPortToQueueId
        self.mainPortToQueueId[switch] = (portNo, queueId)

    def setBackupPortToQueueId(self, switch, portNo, queueId):
        assert  switch not in self.backupPortToQueueId
        self.backupPortToQueueId[switch] = (portNo, queueId)

    def getMainPortToQueueId(self, switch):
        assert switch in self.mainPortToQueueId
        item = self.mainPortToQueueId[switch]
        return item[0], item[1]

    def getBackupPortToQueueId(self, switch):
        assert  switch in self.backupPortToQueueId
        item = self.mainPortToQueueId[switch]
        return item[0], item[1]

class TaskList(dict):

    def __init__(self):
        super(TaskList, self).__init__()

    def getTask(self, taskId):

        if len(self) == 0:
            raise ValueError('No task in this domain')

        if taskId in self:
            taskInstance = self[taskId]
        else:
            msg = 'task %d non_exist' % taskId
            raise ValueError

        return taskInstance

