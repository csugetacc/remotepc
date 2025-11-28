import socket
import numpy as np
import cv2
import struct
import csv
import threading
import json

from pynput.mouse import Listener as MouseListener, Button
from pynput.keyboard import Listener as KeyboardListener, Key
from PySide6 import QtCore, QtWidgets, QtGui

import encrypt


video_port = 5000
control_port = 5001


class ClientWorker(QtCore.QObject):
    frameReady = QtCore.Signal(QtGui.QImage)    # send decoded image 
    statusText = QtCore.Signal(str)     # send text to display in videobox
    closed = QtCore.Signal()    # send closed message 

    def __init__(self, host: str, video_port: int = 5000, control_port: int = 5001, parent=None):
        super().__init__(parent)
        self.host = host    # ip converted in UI
        self.video_port = video_port
        self.control_port = control_port
        self.client_running = False
        self.PSK = encrypt.load_key()
        self.control_socket = None
        self.video_socket = None
        self.pressed_keys = set()   # stores keystrokes to send
        self.window_dims = {'x': 0, 'y': 0, 'w': 1, 'h': 1}         # initalize for mouse window acounting
        self.frame_dims  = {'w': 1, 'h': 1}
        self.state_lock = threading.Lock()

    @QtCore.Slot()
    def start(self):

        self.client_running = True

        try:
            # control connect
            self.statusText.emit(f"Connecting to {self.host}:{self.control_port} ...")
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.connect((self.host, self.control_port))

            # video connect 
            self.statusText.emit(f"Connecting to {self.host}:{self.video_port} ...")
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.video_socket.connect((self.host, self.video_port))

            self.statusText.emit("Connected. Press 'q' to quit.")

            # main receive loop
            while self.client_running:
                jpeg = encrypt.recv_open(self.video_socket, self.PSK, aad=b"video")
                if jpeg is None:
                    break
                arr = np.frombuffer(jpeg, dtype=np.uint8)
                frame_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame_bgr is None:
                    continue

                # get window dimensions for mouse calculations
                h, w = frame_bgr.shape[:2]
                with self.state_lock:
                    self.frame_dims['w'], self.frame_dims['h'] = w, h   # update frame values

                img = frame_to_qimage(frame_bgr)    # convert to image type pyqt can use
                self.frameReady.emit(img)

        except Exception as e:
            self.statusText.emit(f"Client error: {e}")
        finally:
            try:
                if self.video_socket:
                    self.video_socket.close()
            except Exception:
                pass
            try:
                if self.control_socket:
                    self.control_socket.close()
            except Exception:
                pass
            self.closed.emit()

    # close connection
    @QtCore.Slot()
    def stop(self):
        self.client_running = False
        try:
            if self.video_socket:
                self.video_socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            if self.control_socket:
                self.control_socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass


    def send_command(self, obj):
        if not self.control_socket:
            return
        try:
            encrypt.send_json(self.control_socket, self.PSK, obj)
        except Exception:
            pass

    # get window dimensions for mouse calculations (called from UI)
    @QtCore.Slot(int, int, int, int)
    def set_window_rect(self, x, y, w, h):
        with self.state_lock:
            self.window_dims.update({'x': x, 'y': y, 'w': w, 'h': h})   # update window values


    def mouse_move(self, x, y):
        # calculate for mouse in window
        with self.state_lock:
            wx, wy, ww, wh = (self.window_dims['x'], self.window_dims['y'], self.window_dims['w'], self.window_dims['h'])
            fw, fh = self.frame_dims['w'], self.frame_dims['h']

        frame_x = x - wx
        frame_y = y - wy

        if 0 <= frame_x < ww and 0 <= frame_y < wh:  # only send when in window 
            # scale to frame resolution
            adjusted_x = frame_x * (fw / float(ww))
            adjusted_y = frame_y * (fh / float(wh))

            self.send_command({'type': 'mouse_move', 'value': (int(adjusted_x), int(adjusted_y))})

    def mouse_click(self, which: str):
        self.send_command({'type': 'mouse_down', 'value': which})

    def mouse_release(self, which: str):
        self.send_command({'type': 'mouse_up', 'value': which})

    def key_press(self, name: str):
        if name not in self.pressed_keys:    # only send once per press
            self.pressed_keys.add(name)
            self.send_command({'type': 'key_down', 'value': name})

    def key_release(self, name: str):
        if name in self.pressed_keys:   # only delete once per release
            self.pressed_keys.discard(name)
        self.send_command({'type': 'key_up', 'value': name})


# convert opencv frame to qt image 
def frame_to_qimage(frame_bgr: np.ndarray) -> QtGui.QImage:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)


# get device ip from csv
def getip(name, filename = "hosts.csv"):
    with open(filename, newline="") as csvfile:
        for row in csv.reader(csvfile):
            if len(row) >= 2:
                csv_name = row[0].strip()
                ip = row[1].strip()
                if csv_name == name:
                    return ip

''' outdated
def recvall(sock, n):
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)
'''
'''
def client_program(hostname):

    # get host ipv4
    host = getip(hostname)  

    # get passcode
    PSK = encrypt.load_key()

    # temporary catch for bad hostname 
    if not host:
        print("invalid host entered")
        exit()

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
                encrypt.send_json(control_socket, PSK, command)
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
                
            jpeg = encrypt.recv_open(video_socket, PSK, aad=b"video")
            if jpeg is None:
                print("Connection closed while receiving frame.")
                break  # disconnected 

            # display frame
            arr = np.frombuffer(jpeg, dtype=np.uint8)
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
'''