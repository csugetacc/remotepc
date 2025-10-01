import socket
import mss
import numpy as np
import cv2
import struct
import time 


host = "0.0.0.0" # listen on all interfaces
port = 5000

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
    


def server_program():

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(1)
        
        print(f"Server listening on {host}:{port}")
        conn, addr = server_socket.accept()
        
        with conn:
            print("Connection from:", addr)
            
            with mss.mss() as sct:
                frame_interval = 1.0 / FPS

                while True:
                    t0 = time.time()

                    data = screen_grab(sct)
                    if data is None:
                        continue
    
                    # send prefix + payload
                    conn.sendall(struct.pack("!I", len(data)))
                    conn.sendall(data)

                    # throttle FPS
                    elapsed = time.time() - t0
                    sleep = frame_interval - elapsed
                    if sleep > 0:
                        time.sleep(sleep)

server_program()

