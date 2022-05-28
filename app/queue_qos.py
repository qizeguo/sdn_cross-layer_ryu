__author__ = 'Johnny'


from ryu.ofproto import ofproto_v1_0
from ryu.ofproto import ofproto_v1_2
from ryu.ofproto import ofproto_v1_3
from ryu.lib import ofctl_v1_0
from ryu.lib import ofctl_v1_2
from ryu.lib import ofctl_v1_3

from ryu.lib.ovs import bridge
from ryu.exception import OFPUnknownVersion
REST_PORT_NAME = 'port_name'
REST_QUEUE_TYPE = 'type'
REST_QUEUE_MAX_RATE = 'max_rate'
REST_QUEUE_MIN_RATE = 'min_rate'
REST_QUEUE_ID = 'qos_id'
REST_PARENT_MAX_RATE = 'parent_max_queue'


class QueueQos(object):

    _OFCTL = {ofproto_v1_0.OFP_VERSION: ofctl_v1_0,
              ofproto_v1_2.OFP_VERSION: ofctl_v1_2,
              ofproto_v1_3.OFP_VERSION: ofctl_v1_3}

    def __init__(self, dp, CONF):
        super(QueueQos, self).__init__()
        # self.vlan_list = {}
        self.dp = dp
        self.version = dp.ofproto.OFP_VERSION
        # self.queue_list = {}

        self.queueInfo = {}   ##  portNo < --- > QueuePort
        self.CONF = CONF
        self.ovsdb_addr = None
        self.ovs_bridge = None

        if self.version not in self._OFCTL:
            raise OFPUnknownVersion(version=self.version)

        self.ofctl = self._OFCTL[self.version]

    def set_ovsdb_addr(self, dpid, ovsdb_addr):
        # easy check if the address format valid
        _proto, _host, _port = ovsdb_addr.split(':')

        old_address = self.ovsdb_addr
        if old_address == ovsdb_addr:
            return
        if ovsdb_addr is None:
            if self.ovs_bridge:
                self.ovs_bridge.del_controller()
                self.ovs_bridge = None
            return
        self.ovsdb_addr = ovsdb_addr
        if self.ovs_bridge is None:
            ovs_bridge = bridge.OVSBridge(self.CONF, dpid, ovsdb_addr)
            self.ovs_bridge = ovs_bridge
            try:
                ovs_bridge.init()
            except:
                raise ValueError('ovsdb addr is not available.')

    def set_queue(self, rest):
        if self.ovs_bridge is None:
            status = 'no ovs bridge'
            return 1, status
        queue_type = rest.get(REST_QUEUE_TYPE, 'linux-htb')
        parent_max_rate = str(rest.get(REST_PARENT_MAX_RATE, None))

        queue_config = []
        max_rate = str(rest.get(REST_QUEUE_MAX_RATE, None))
        min_rate = str(rest.get(REST_QUEUE_MIN_RATE, None))
        queue_id = rest.get(REST_QUEUE_ID, None)

        if max_rate is None and min_rate is None:
            status = 'bad queue config'
            return 2, status

        config = {}

        if max_rate is not None:
            config['max-rate'] = max_rate

        if min_rate is not None:
            config['min-rate'] = min_rate
        if queue_id is not None:
            config['queue-id'] = queue_id
        queue_config.append(config)

        port_name = rest.get(REST_PORT_NAME, None)

        if port_name is None:
            status = 'Need specify port_name'
            return 3, status

        try:
            self.ovs_bridge.set_qos(port_name, type=queue_type,
                                    max_rate=parent_max_rate,
                                    queues=queue_config)
        except Exception as msg:
            print msg.message
            raise ValueError

        status = 'queue set success'
        return 0, status

    def get_queueid(self, portNo):
        queuePort = self.queueInfo.get(portNo)
        queueList = queuePort.getList()
        ##print queuePort.__dict__
        # print "here"
        # print 'queueList: ',queueList
        for i in sorted(queueList.keys()):
            queueInfo = queueList[i]
            if not queueInfo.checkInUse():
                # queueInfo['max'] = maxRate
                # queueInfo['min'] = minRate
                return i

        return -1
        # newId = len(queueList)
        # if newId == 8:
        #     return -1
        # else:
        #     queueList[newId] = QueueInfo(newId, maxRate, minRate, False)
        #     return newId


    def make_queue_rest(self, portName, maxRate, minRate, queueId, parentMaxRate=10000000):
        rest = {}
        rest[REST_PORT_NAME] = portName
        rest[REST_QUEUE_MAX_RATE] = str(maxRate)
        rest[REST_QUEUE_MIN_RATE] = str(minRate)
        rest[REST_PARENT_MAX_RATE] = str(parentMaxRate)
        rest[REST_QUEUE_ID] = queueId

        return rest

    def setQueueInUse(self, portNo, queueId):
        assert portNo in self.queueInfo
        queuePort = self.queueInfo[portNo]
        queuelist = queuePort.getList()
        queueInfo = queuelist[queueId]
        queueInfo.changeIntoInUse()


class QueuePort(object):

    def __init__(self, portNo, dpid):

        self.portNo = portNo
        self.dpid = dpid
        self.queueList = {}   #  queueId < ----- > queueInfo

    def getList(self):
        return self.queueList

class QueueInfo(object):

    def __init__(self,maxRate, minRate, inUse=False):

       # self.id = id
        self.maxRate = maxRate
        self.minRate= minRate
        self.inUse = inUse

    def checkInUse(self):
        return self.inUse

    def changeIntoInUse(self):

        assert not self.inUse

        self.inUse = True