import socket
import numpy as np
import cv2
import struct
import csv

import json
from pynput.mouse import Listener as MouseListener, Button

hostname = "linux" # hardcoded laptop IPv4
video_port = 5000
control_port = 5001

# get device ip from csv
def getip(name, filename = "hosts.csv"):
    with open(filename, newline="") as csvfile:
        for row in csv.reader(csvfile):
            if len(row) >= 2:
                csv_name = row[0].strip()
                ip = row[1].strip()
                if csv_name == name:
                    return ip

def recvall(sock, n):
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)

def client_program():

    host = getip(hostname)

    # start connections
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_socket, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as video_socket:     

        #mouse portion
        print(f"Connecting to {host}:{control_port} ...")
        control_socket.connect((host, control_port))

        def send_mouse(command):
            try:
                control_socket.sendall((json.dumps(command) + "\n").encode("utf-8"))
            except OSError:
                print("OSError detected")
                pass

        def on_move(x, y):
            send_mouse({'type': 'mouse_move', 'value': (x, y)})

        def on_click(x, y, button, pressed):
            if pressed:
                send_mouse({'type': 'mouse_click', 'value': 'left' if button == Button.left else 'right'})

        listener = MouseListener(on_move=on_move, on_click=on_click)
        listener.start()

        
        # video portion 
        print(f"Connecting to {host}:{video_port} ...")
        video_socket.connect((host, video_port))
        print("Connected. Press 'q' to quit.")

        while True:
            # read first 4 bytes
            raw_len = recvall(video_socket, 4)

            if not raw_len: # if null kill
                print("Connection closed by server.")
                break

            (frame_len,) = struct.unpack("!I", raw_len)

            # read data
            payload = recvall(video_socket, frame_len)
            if payload is None:
                print("Connection closed while receiving frame.")
                break

            # display frame
            arr = np.frombuffer(payload, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue
            cv2.imshow("Remote Screen", frame)
            
            # close connection
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        # close out 
        #finally:
        listener.stop()
        cv2.destroyAllWindows()


client_program()
