import socket

def client_program():
    host = "" # hardcoded laptop IPv4
    port = 5000

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        
        print(f"Connecting to {host}:{port} ...")
        client_socket.connect((host, port))
        msg = input(" -> ")
        
        while msg.lower().strip() != "exit": # close connection 
            
            client_socket.sendall(msg.encode())
            data = client_socket.recv(1024).decode(errors="ignore")
            print("Received from server:", data)
            msg = input(" -> ")

client_program()
