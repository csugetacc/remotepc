import socket

def server_program():
    host = "0.0.0.0" # listen on all interfaces
    port = 5000

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(2)
        
        print(f"Server listening on {host}:{port}")
        conn, address = server_socket.accept()
        
        with conn:
            
            print("Connection from:", address)
            
            while True:
                
                data = conn.recv(1024)
                
                if not data:
                    break
                
                print("from connected user:", data.decode(errors="ignore"))
                reply = input(" -> ")
                
                conn.sendall(reply.encode())


server_program()

