__author__ = 'Johnny'


import networkx as nx
import copy


class TopoInfo(object):

    def __init__(self):

        self.name = "AllTopo"
        self.topo = nx.DiGraph()
        self.nodeToDomainId = {}
        self.linkWithPort = []


    def addNode(self, node, domainID, attr=None):
        if attr:
            assert isinstance(attr, dict)

        if node not in self.topo.nodes():
            self.topo.add_node(node, attr_dit=dict)

        if node not in self.nodeToDomainId.keys():
            self.nodeToDomainId[node] = domainID

    def removeNode(self, node, domainId):

        if node in self.topo.nodes():
            self.topo.remove_node(node)

        assert node in self.nodeToDomainId.keys()

        del self.nodeToDomainId[node]


    def addEdge(self, src, srcPortNo, dst, dstPortNo):

        assert src is not dst
        edge = (src, dst)

        if edge not in self.topo.edges():
            self.topo.add_edge(src, dst)

        linkPort = (src, srcPortNo, dst, dstPortNo)
        if linkPort not in self.linkWithPort:
            self.linkWithPort.append(linkPort)

    def removeEdge(self, src, srcPortNo, dst, dstPortNo):
        assert src is not dst

        edge = (src, dst)
        if edge in self.topo.edges():
            self.topo.remove_edge(src, dst)


        linkPort = (src, srcPortNo, dst, dstPortNo)

        if linkPort in self.linkWithPort:
            self.linkWithPort.remove(linkPort)

    def getShortestPath(self, src, dst):
        try:
            nodeList = nx.shortest_path(self.topo, src, dst)
        except:
            nodeList = []

        return nodeList


    def getWeightPath(self, src, dst):
        try:
            nodeList = nx.dijkstra_path(self.topo, src, dst)
        except:

            nodeList = []

        return nodeList

    def getNewTopoExceptSE(self, edges):

        # newTopo = self.topo.copy()
        # try:
        #     newTopo.remove_edges_from(edges)
        # except:
        #     newTopo = None
        #
        # return newTopo
        newTopo = copy.deepcopy(self)
        newTopo.topo.remove_edges_from(edges)
        return newTopo



    def updateWeight(self, ebunch):

        for item in ebunch:
            assert len(item) == 3
            assert isinstance(item, tuple)
            assert 'weight' in item[2]

        self.topo.add_edges_from(ebunch)

    def getLinkSrc(self, node, portNo):
        for i in self.linkWithPort:
            if i[2] == node and i[3] == portNo:
                srcNode = i[0]
                srcPort = i[1]
                return srcNode, srcPort
        return None, None

    def getEdgeFromDstPoint(self, node, portNo):
        srcNode, srcPort = self.getLinkSrc(node, portNo)
        if not srcNode or not srcPort:
            return None
        return (srcNode, node)

    def nodes(self):
        return self.topo.nodes()

    def edges(self):
        return self.topo.edges()

    def isNodeIn(self, node):
        return node in self.nodes()

