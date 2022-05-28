__author__ = 'root'


class SwitchFeatures(object):

    def __init__(self, dpid):
        self.dpid = dpid
        self.name = None
        self.version = None
        self.capablities = None
        self.n_buffers = None
        self.n_tables = None
        self.auxiliary_id = None
        self.ports ={}

    def getPort(self, portNo):
        assert portNo in self.ports
        return self.ports[portNo]

    def getPorts(self):
        return self.ports

    def setName(self, name):
        self.name = name

    def getPortName(self, portNo):
        port = self.getPort(portNo)
        return port.getName()

    def _set_version(self, version):
        self.version = version

    def _set_capablities(self, cap):
        self.capablities = cap

    def _set_nbuffers(self, n_buffer):
        self.n_buffers = n_buffer

    def _set_ntalbe(self, ntables):
        self.n_tables = ntables

    def _set_auxiliar_id(self, aux_id):
        self.auxiliary_id = aux_id

    def initFieds(self, version, capablities, n_buffers, n_tables, auxiliary_id):
        self._set_version(version)
        self._set_capablities(capablities)
        self._set_nbuffers(n_buffers)
        self._set_ntalbe(n_tables)
        self._set_auxiliar_id(auxiliary_id)

    def makeFeaturesMessage(self):
        message = {}
        message['name'] = self.name
        portsInfo = message.setdefault('ports', {})
        ports = self.getPorts()
        for i in ports:
            port = ports[i]
            portInfo = portsInfo.setdefault(i, {})
            portInfo['name'] = port.name
            portInfo['hw_addr'] = port.hw_addr
            portInfo['config'] = port.config
            portInfo['curr'] = port.curr
            portInfo['max_speed'] = port.max_speed
            portInfo['curr_speed'] = port.curr_speed

        return message

class PortFeatures(object):

    def __init__(self, portNo):

        self.port_no = portNo
        self.name = None
        self.hw_addr = None
        self.config = None
        self.state = None
        self.curr = None
        self.advertiesd = None
        self.supported = None
        self.peer = None
        self.curr_speed = None
        self.max_speed = None


    def initFields(self, port):
        self.name = port.name
        self.hw_addr = port.hw_addr
        self.config = port.config
        self.state = port.state
        self.curr = port.curr
        self.advertiesd = port.advertised
        self.supported = port.supported
        self.peer = port.peer
        self.curr_speed = port.curr_speed
        self.max_speed = port.max_speed

    def getName(self):
        return self.name

