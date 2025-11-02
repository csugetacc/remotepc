import socket
import mss
import numpy as np
import cv2
import struct
import time 
import json
import threading 

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Controller as KeyboardController, Key as Key

HOST = "0.0.0.0" # listen on all interfaces
VIDEO_PORT = 5000   # send video on 5000
CONTROL_PORT = 5001 # send inputs on 5001

mouse = MouseController()
keyboard = KeyboardController()

# set values for streaming 
FPS = 15
SCALE = .6
JPEG_QUALITY = 70

# initalize mouse calculation values 
screen_w = 1
screen_h = 1
frame_w = 1
frame_h = 1


# get screen frame to send
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

    global screen_w, screen_h, frame_w, frame_h     #use global values
    t = command.get('type')
    v = command.get('value')

    if t == 'mouse_move':
        x, y = v

        # account for screen size
        sx = int(x * (screen_w / float(frame_w)))
        sy = int(y * (screen_h / float(frame_h)))

        mouse.position = (int(sx), int(sy))

    elif t == 'mouse_down':
        mouse.press(Button.left if v == 'left' else Button.right)
    
    elif t == 'mouse_up':
        mouse.release(Button.left if v == 'left' else Button.right)

    # keyboard controlls are going in here for now 
    elif t == 'key_down':
        key = handle_keyboard_control(v)
        try:
            keyboard.press(key)
        except ValueError:
            # ignore keys pynput cant press
            pass

    elif t == 'key_up':
        key = handle_keyboard_control(v)
        try:
            keyboard.release(key)
        except ValueError:
            pass


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

def handle_keyboard_control(name: str):
    # try special keys
    try:
        return getattr(Key, name)
    except AttributeError:
        pass
    # try function keys
    if name.startswith('f') and name[1:].isdigit():
        try:
            return getattr(Key, name)
        except AttributeError:
            pass
    # else treat as literal character
    return name


def server_program():

    # initalize sockets
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_socket, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as video_socket:

        #control setup
        control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        control_socket.bind((HOST, CONTROL_PORT))
        control_socket.listen(1)
        
        # video setup
        video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        video_socket.bind((HOST, VIDEO_PORT))
        video_socket.listen(1)

        # control connect
        print(f"Control listening on {HOST}:{CONTROL_PORT}")
        control_conn, control_addr = control_socket.accept()

        print("Control connection from:", control_addr)
        threading.Thread(target=handle_mouse_control, args=(control_conn,), daemon=True).start() # handle controls in seperate thread

        # video connect
        print(f"Video listening on {HOST}:{VIDEO_PORT}")
        video_conn, video_addr = video_socket.accept()

        print("Video connection from:", video_addr)
        
        with video_conn:
            with mss.mss() as sct:
                frame_interval = 1.0 / FPS

                mon = sct.monitors[1]   #only main monitor for now 

                global screen_w, screen_h, frame_w, frame_h     # use global values

                # get screen size
                screen_w = mon['width']
                screen_h = mon['height']
                frame_w = int(screen_w * SCALE)
                frame_h = int(screen_h * SCALE)

                # share screen size 
                screen_w, screen_h = screen_w, screen_h
                frame_w, frame_h = frame_w, frame_h

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
