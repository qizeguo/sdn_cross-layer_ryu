__author__ = 'root'
Peer_Table = {('10.108.90.1', '10.108.91.1'): (512, 4, 769, 6),
            ('10.108.91.1', '10.108.90.1'): (769, 6, 512, 4)}


for key in Peer_Table:
    print Peer_Table[key][2]

print type((512, 4, 769, 6))

# class test(object):
#     def __init__(self):
#         self.taskid=0

def get_taskid(self):
    self.taskid=0
    self.taskid += 1

    return self.taskid

def sss(self):
    self.get_taskid()
    taskidd = self.get_taskid()
    print taskidd

def main():
    if __name__ == '__main__':
        sss()


from ryu.base import app_manager

class L2Switch(app_manager.RyuApp):
    def __init__(self, *args, **kwargs):
        super(L2Switch, self).__init__(*args, **kwargs)


