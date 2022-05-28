__author__ = 'Johnny'

import random

class TaskPool(object):

    def __init__(self, *args, **kwargs):
        self.taskid = 0

    def initTaskPool(self):
        item = random.randint(0, 1000)
        if item not in self.initTaskPool:
            self.initTaskPool.append(item)

    def get_taskid(self):

        taskid = self.initTaskPool[0]
        self.initTaskPool.remove(taskid)

        return taskid
