import socket
import mss
import numpy as np
import cv2
import struct
import time 

import json
import threading 

from pynput.mouse import Button, Controller as MouseController

host = "0.0.0.0" # listen on all interfaces
video_port = 5000   # send video on 5000
control_port = 5001 # send inputs on 5001

mouse = MouseController()

# set values for streaming 
FPS = 15
SCALE = .6
JPEG_QUALITY = 70


def screen_grab(sct, scale = SCALE, jpg_q = JPEG_QUALITY):

    mon = sct.monitors[1]  # primary display
    img = np.array(sct.grab(mon))
    frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # downscale
    if SCALE != 1.0:
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (int(w*SCALE), int(h*SCALE)), interpolation=cv2.INTER_AREA)

    # JPEG encode
    ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        return None
    return enc.tobytes()
    

def mouse_control(command):
    t = command.get('type')
    v = command.get('value')
    if t == 'mouse_move':
        x, y = v
        mouse.position = (int(x), int(y))
    elif t == 'mouse_click':
        mouse.click(Button.left if v == 'left' else Button.right, 1)

def handle_mouse_control(conn):
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line:
                    continue
                try:
                    cmd = json.loads(line.decode("utf-8"))
                    mouse_control(cmd)
                except json.JSONDecodeError:
                    # ignore malformed lines
                    pass
    finally:
        conn.close()

def server_program():

    # initalize sockets
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_socket, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as video_socket:

        #control setup
        control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        control_socket.bind((host, control_port))
        control_socket.listen(1)
        
        # video setup
        video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        video_socket.bind((host, video_port))
        video_socket.listen(1)

        # control connect
        print(f"Control listening on {host}:{control_port}")
        control_conn, control_addr = control_socket.accept()

        print("Control connection from:", control_addr)
        threading.Thread(target=handle_mouse_control, args=(control_conn,), daemon=True).start()

        # video connect
        print(f"Video listening on {host}:{video_port}")
        video_conn, video_addr = video_socket.accept()

        print("Video connection from:", video_addr)
        
        with video_conn:
            with mss.mss() as sct:
                frame_interval = 1.0 / FPS

                while True:
                    t0 = time.time()

                    data = screen_grab(sct)
                    if data is None:
                        continue

                    # send prefix + payload
                    video_conn.sendall(struct.pack("!I", len(data)))
                    video_conn.sendall(data)

                    # throttle FPS
                    elapsed = time.time() - t0
                    sleep = frame_interval - elapsed
                    if sleep > 0:
                        time.sleep(sleep)

server_program()

