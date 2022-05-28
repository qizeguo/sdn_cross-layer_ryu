__author__ = 'hyq'

import eventlet
#BGPspeaker needs sockets patched
eventlet.monkey_patch()

#initialize a log handler
#this is not strictly necessary but useful if you get message like:
#no handlers could be found for logger "ryu,lib.hub"

import logging
import sys
log = logging.getLogger()
log.addHandler(logging.StreamHandler(sys.stderr))

from ryu.services.protocols.bgp.bgpspeaker import BGPSpeaker


def dump_remote_best_path_change(event):
    print 'the best path changed:',event.remote_as,event.prefix,event.nexthop,event.is_withdraw

def detect_peer_down(remote_ip,remote_as):
    print 'Peer down:',remote_ip,remote_as

if __name__=="__main__":
    speaker = BGPSpeaker(as_number=20,router_id='1.1.1.1',
                         best_path_change_handler=dump_remote_best_path_change,
                         peer_down_handler=detect_peer_down
                         )
    speaker.neighbor_add("10.108.90.1",10)
    speaker.neighbor_add("10.108.91.1",30)
    #speaker.neighbor_add("10.108.92.1",40)



    #print speaker.rib_get()
    #speaker.neighbor_add("10.108.91.1",30)




    #uncomment the below line if the speaker needs to talk with a bmp server
    #speaker.bmp_server_add('192.168.177.2',11019)

    count=1
    while True:
        eventlet.sleep(10)
        prefix = '10.108.' + str(count) + '.0/24'
        print "add a new prefix",prefix
        speaker.prefix_add(prefix)
        count+=1
        if count == 10:
            speaker.shutdown()
            break

