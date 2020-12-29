import zmq
import sys

socket = zmq.Context.instance().socket(zmq.REQ)
socket.connect('tcp://127.0.0.1:6969')
socket.send_string(' '.join(sys.argv[1:]))
print(socket.recv_string())
