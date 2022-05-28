__author__ = 'Johnny'

import  networkx as nx



class DomainTopo(object):

    def __init__(self, name=None, *args, **kwargs):

        self.topo = nx.DiGraph()
        self.name = "AllTopo"
        self.linkWithPort = []


    def addNode(self, node, attr=None):
        if attr:
            assert isinstance(attr, dict)

        if node not in self.topo.nodes():
            self.topo.add_node(node, attr_dit=dict)


    def removeNode(self, node):
        if node in self.topo.nodes():
            self.topo.remove_node(node)


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

    def isNodeIn(self, node):
        return node in self.topo.nodes()



    def updateTopo(self, ebunch):

        for item in ebunch:
            assert len(item) == 3
            assert isinstance(item, dict)
            assert 'weight' in item[2]

        self.topo.add_edges_from(ebunch)

    def getNewTopoExceptSE(self, edges):

        newTopo = self.topo.copy()
        try:
            newTopo.remove_edges_from(edges)
        except:
            newTopo = None

        return None
    def nodes(self):
        return self.topo.nodes()

    def edges(self):
        return self.topo.edges()

    def getLinkOutPort(self, linkSrc, linkDst):

        for i in self.linkWithPort:
            if i[0] == linkDst and i[2] == linkSrc:
                return i[3]

        return None