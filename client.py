import socket
import numpy as np
import cv2
import struct
import csv
import threading
import json
from pynput.mouse import Listener as MouseListener, Button
from pynput.keyboard import Listener as KeyboardListener, Key

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

    # get host ipv4
    hostname = input("Enter device name: ")
    host = getip(hostname)  

    pressed_keys = set() # stores keystrokes to send

    # initalize for mouse window acounting
    window_dims = {'x': 0, 'y': 0, 'w': 1, 'h': 1}
    frame_dims  = {'w': 1, 'h': 1}
    state_lock = threading.Lock()

    # start connections
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_socket, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as video_socket:     

        # mouse functions
        def send_mouse(command):
            try:
                control_socket.sendall((json.dumps(command) + "\n").encode("utf-8"))
            except OSError:
                print("OSError detected")
                pass

        def on_move(x, y):
            # calculate for mouse in window
            with state_lock:
                wx, wy, ww, wh = window_dims['x'], window_dims['y'], window_dims['w'], window_dims['h']
                fw, fh = frame_dims['w'], frame_dims['h']

            frame_x = x - wx
            frame_y = y - wy

            if 0 <= frame_x < ww and 0 <= frame_y < wh:   # only send when in window 
                # scale to frame resolution
                adjusted_x = frame_x * (fw / float(ww))
                adjusted_y = frame_y * (fh / float(wh))

                send_mouse({'type': 'mouse_move', 'value': (int(adjusted_x), int(adjusted_y))})

        def on_click(x, y, button, pressed):
            if pressed:
                send_mouse({'type': 'mouse_down', 'value': 'left' if button == Button.left else 'right'})
            else:   # register click release
                send_mouse({'type': 'mouse_up', 'value': 'left' if button == Button.left else 'right'})    

        # keyboard functions
        def key_to_name(key):
            # assign char to key 
            try:
                if hasattr(key, 'char') and key.char is not None:
                    return key.char
            except AttributeError: # ignore non characters
                pass
            try:
                return key.name  # get special keys name
            except AttributeError:
                return str(key)  # if all else fails turn key to string

        def on_key_press(key):
            name = key_to_name(key)
            if name not in pressed_keys:    # only send once per press
                pressed_keys.add(name)
                send_mouse({'type': 'key_down', 'value': name})

        def on_key_release(key):
            name = key_to_name(key)
            if name in pressed_keys:        # only delete once per release
                pressed_keys.discard(name)
            send_mouse({'type': 'key_up', 'value': name})


        # start listners 
        listener = MouseListener(on_move=on_move, on_click=on_click)
        listener.start()
        key_listener = KeyboardListener(on_press=on_key_press, on_release=on_key_release)
        key_listener.start()
        
        # connect control port
        print(f"Connecting to {host}:{control_port} ...")
        control_socket.connect((host, control_port))

        # video connection 
        print(f"Connecting to {host}:{video_port} ...")
        video_socket.connect((host, video_port))
        print("Connected. Press 'q' to quit.")

        # start window
        cv2.namedWindow("Remote Screen", cv2.WINDOW_NORMAL) 

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

            # get window dimensions for mouse calculations
            h, w = frame.shape[:2]
            with state_lock:
                frame_dims['w'], frame_dims['h'] = w, h     # update frame values
                try:
                    wx, wy, ww, wh = cv2.getWindowImageRect("Remote Screen")
                    window_dims.update({'x': wx, 'y': wy, 'w': ww, 'h': wh})    # update window values 
                except Exception:
                    pass

            # close connection
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        # close out 
        listener.stop()
        key_listener.stop()
        cv2.destroyAllWindows()


client_program()
