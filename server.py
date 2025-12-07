import socket
import mss
import numpy as np
import cv2
import struct
import time 
import json
import threading 
import os
import encrypt

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Controller as KeyboardController, Key as Key


HOST = "0.0.0.0" # listen on all interfaces
VIDEO_PORT = 5000   # send video on 5000
CONTROL_PORT = 5001 # send inputs on 5001

mouse = MouseController()
keyboard = KeyboardController()

# initalize mouse calculation values 
screen_w = 1
screen_h = 1
frame_w = 1
frame_h = 1

# track if the server is on 
server_running = False


# get screen frame to send
def screen_grab(sct, scale, jpg_q):

    mon = sct.monitors[1]  # primary display
    img = np.array(sct.grab(mon))
    frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # downscale
    if scale != 1.0:
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)

    # JPEG encode
    ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpg_q])
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


def handle_mouse_control(control_conn, PSK):
    try:
        while True:
            cmd = encrypt.recv_json(control_conn, PSK)

            if cmd is None: # catch bad recv 
                break

            # im going to put the file recieve commands in here, for now...

            cmd_typ = cmd.get("type")

            # process incoming file
            if cmd_typ == "file_start":
                recv_file(control_conn, PSK, cmd)

            # process mouse / keyboard movements
            elif cmd_typ in ("mouse_move", "mouse_down", "mouse_up", "key_down", "key_up"):
                mouse_control(cmd)

            # log file completion 
            elif cmd_typ == "file_end":
                print(f"File transfer complete: {cmd.get('name')}")

            else:
                # unknown command, theoretically this cant happen
                print(f"Unknown control command: {cmd}")

    finally:
        control_conn.close() 


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


def recv_file(control_conn, PSK, header: dict):

    # get file info
    filename = header.get("name", "received.bin")
    size = int(header.get("size", 0))

    # save location
    os.makedirs("received_files", exist_ok=True)
    path = os.path.join("received_files", filename)

    remaining = size

    with open(path, "wb") as f:
        
        while remaining > 0:

            chunk = encrypt.recv_open(control_conn, PSK, aad=b"file")

            # this should only be hit if the program closes prematurly
            if chunk is None:
                print("Connection closed while receiving file.")
                break

            f.write(chunk)
            remaining -= len(chunk)

    print(f"Saved file to {path}")


def stop_server():
    global server_running
    server_running = False


def server_program(FPS, scale, jepg_q):

    # set status
    global server_running
    server_running = True

    # load key
    PSK = encrypt.load_key()

    # initalize sockets
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as control_socket, \
         socket.socket(socket.AF_INET, socket.SOCK_STREAM) as video_socket:

        # adjust timeouts
        control_socket.settimeout(1.0)
        video_socket.settimeout(1.0)

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
        control_conn = None

        while server_running and control_conn is None:
            try:
                control_conn, control_addr = control_socket.accept()
                print("Control connection from:", control_addr)
            except socket.timeout:
                continue

        # exit loop if server stopped
        if not server_running:
            return

        threading.Thread(target=handle_mouse_control, args=(control_conn, PSK), daemon=True).start() # handle controls in seperate thread

        # video connect
        print(f"Video listening on {HOST}:{VIDEO_PORT}")
        video_conn = None

        while server_running and video_conn is None:
            try:
                video_conn, video_addr = video_socket.accept()
                print("Video connection from:", video_addr)
            except socket.timeout:
                continue

        # exit loop if server stopped
        if not server_running:
            return

        
        with video_conn:
            with mss.mss() as sct:
                frame_interval = 1.0 / FPS

                mon = sct.monitors[1]   #only main monitor for now 

                global screen_w, screen_h, frame_w, frame_h     # use global values

                # get screen size
                screen_w = mon['width']
                screen_h = mon['height']
                frame_w = int(screen_w * scale)
                frame_h = int(screen_h * scale)

                # share screen size 
                screen_w, screen_h = screen_w, screen_h
                frame_w, frame_h = frame_w, frame_h

                while server_running:

                    t0 = time.time()

                    data = screen_grab(sct, scale, jepg_q)
                    if data is None:
                        continue

                    try:
                        encrypt.send_sealed(video_conn, PSK, data, aad=b"video")
                    except OSError:
                        break

                    # throttle FPS
                    elapsed = time.time() - t0
                    sleep = frame_interval - elapsed
                    if sleep > 0:
                        time.sleep(sleep)
