__author__ = 'Johnny'

import random


class MplsLabelsPool(object):

    def __init__(self, numbers = 1000, minimal = 1000, maxmal = 9999, *args, **kwargs):

        self.labelsPool = []
        self.numbers = numbers
        self.minimal = minimal
        self.maxmal = maxmal

    def initPool(self):
        while len(self.labelsPool) < self.numbers:
            item = random.randint(self.minimal, self.maxmal + 1)
            if item not in self.labelsPool:
                self.labelsPool.append(item)
    
    def getLabels(self, n):

        assert len(self.labelsPool) >= n
        lables = []
        while n > 0:
            label = self.labelsPool[0]
            self.labelsPool.remove(label)
            lables.append(label)
            n = n - 1

        return lables

    def recycleLabels(self, labelsList):
        for i in labelsList:
            self.labelsPool.append(i)

