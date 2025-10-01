import socket
import numpy as np
import cv2
import struct
import csv

hostname = "linux" # hardcoded laptop IPv4
port = 5000

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
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        
        print(f"Connecting to {host}:{port} ...")
        client_socket.connect((host, port))
        print("Connected. Press 'q' to quit.")

        while True:
            # read first 4 bytes
            raw_len = recvall(client_socket, 4)

            if not raw_len: # if null kill
                print("Connection closed by server.")
                break

            (frame_len,) = struct.unpack("!I", raw_len)

            # read data
            payload = recvall(client_socket, frame_len)
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

        cv2.destroyAllWindows()

client_program()
