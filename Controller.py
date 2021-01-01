import zmq
import sys

socket = zmq.Context.instance().socket(zmq.REQ)
if sys.argv[1].startswith("-h"):
    if sys.argv[1] == "-h":
        socket.connect('tcp://' + sys.argv[2] + ':6969')
        socket.send_string(' '.join(sys.argv[3:]))
    else:
        socket.connect('tcp://' + sys.argv[1][2:] + ':6969')
        socket.send_string(' '.join(sys.argv[2:]))
else:
    socket.connect('tcp://127.0.0.1:6969')
    socket.send_string(' '.join(sys.argv[1:]))
print(socket.recv_string())
