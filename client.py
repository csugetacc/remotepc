import socket
import numpy as np
import cv2
import struct
import csv
import threading
import json
import os
import encrypt

from pynput.mouse import Listener as MouseListener, Button
from pynput.keyboard import Listener as KeyboardListener, Key
from PySide6 import QtCore, QtWidgets, QtGui


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

            self.statusText.emit("Connected.")

            # control thread recieves data from the server 
            control_thread = threading.Thread(target=self.control_loop, daemon=True)
            control_thread.start()

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


    # send files along the control socket
    def send_file_to_server(self, path: str):

        # make sure this is the correct socket
        if not self.control_socket:
            return

        try:
            # get file info
            size = os.path.getsize(path)
            name = os.path.basename(path)

            # send file info 
            encrypt.send_json(self.control_socket, self.PSK, {
                "type": "file_start",
                "name": name,
                "size": size,
            })

            # send file in chunks
            with open(path, "rb") as f:

                while True:

                    chunk = f.read(64 * 1024)

                    # close transmission once finished
                    if not chunk:
                        break

                    encrypt.send_sealed(self.control_socket, self.PSK, chunk, aad=b"file")

            # indicate that the file has completed transmission
            encrypt.send_json(self.control_socket, self.PSK, {
                "type": "file_end",
                "name": name,
            })

        # 'handel' file send has broken
        except Exception as err:
            print(f"Error sending file: {err}")


    def recv_file_from_server(self, header: dict):

        # get file info
        filename = header.get("name", "downloaded.bin")
        size = int(header.get("size", 0))

        # save location
        os.makedirs("downloads", exist_ok=True)
        path = os.path.join("downloads", filename)

        remaining = size

        with open(path, "wb") as f:

            while remaining > 0 and self.client_running:

                chunk = encrypt.recv_open(self.control_socket, self.PSK, aad=b"file")

                # this should only be hit if the program closes prematurly
                if chunk is None:
                    print("Connection closed while receiving file.")
                    break

                f.write(chunk)
                remaining -= len(chunk)

        print(f"Saved file to {path}")

    
    def control_loop(self):
        try:
            while self.client_running:

                cmd = encrypt.recv_json(self.control_socket, self.PSK)
                if cmd is None:
                    break

                t = cmd.get("type")

                # prepare to recieve file
                if t == "file_start":
                    self.recv_file_from_server(cmd)

                # acknowledge file completion
                elif t == "file_end":
                    name = cmd.get("name")
                    print(f"Download complete: {name}")

        except Exception as e:
            print(f"Control loop error: {e}")



# convert opencv frame to qt image 
def frame_to_qimage(frame_bgr: np.ndarray) -> QtGui.QImage:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)


# get device ip from csv
def getip(name, use_public: bool | None = None):

    with open("hosts.csv", newline="") as csvfile:
        for row in csv.DictReader(csvfile):

            csv_name = row.get("hostname", "").strip()
            if csv_name != name:    # loop untill correct index
                continue

            private_ip = (row.get("privateip") or "").strip() or None
            public_ip  = (row.get("publicip") or "").strip() or None

            '''
            return the desired ip if avalible else return whats avalible 
            prioritize private if user does not select
            '''
            if use_public is True:
                return public_ip or private_ip
            elif use_public is False:
                return private_ip or public_ip
            else:   
                return private_ip or public_ip

    return None     # ip not found