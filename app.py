import socket
import select
import threading
import argparse

class TCPTunnel:
    def __init__(self, local_host, local_port, remote_host, remote_port, buffer_size=4096):
        self.local_host = local_host
        self.local_port = local_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.buffer_size = buffer_size

    def start(self):
        try:
            # Create local server socket
            local_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            local_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            local_socket.bind((self.local_host, self.local_port))
            local_socket.listen(1)
            
            print(f"[*] Listening on {self.local_host}:{self.local_port}")
            
            while True:
                client_socket, addr = local_socket.accept()
                print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")
                
                # Create remote socket
                remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote_socket.connect((self.remote_host, self.remote_port))
                print(f"[*] Connected to remote {self.remote_host}:{self.remote_port}")
                
                # Start forwarding data in both directions
                self.forward_data(client_socket, remote_socket)
                
        except Exception as e:
            print(f"[!] Error: {str(e)}")
            if 'local_socket' in locals():
                local_socket.close()

    def forward_data(self, client_socket, remote_socket):
        def forward(source, destination):
            try:
                while True:
                    data = source.recv(self.buffer_size)
                    if not data:
                        break
                    destination.send(data)
            except:
                pass
            finally:
                source.close()
                destination.close()

        # Create two threads for bidirectional data forwarding
        threading.Thread(target=forward, args=(client_socket, remote_socket), daemon=True).start()
        threading.Thread(target=forward, args=(remote_socket, client_socket), daemon=True).start()

def main():
    parser = argparse.ArgumentParser(description='Simple TCP Tunnel')
    parser.add_argument('--local-host', default='127.0.0.1', help='Local host to listen on')
    parser.add_argument('--local-port', type=int, required=True, help='Local port to listen on')
    parser.add_argument('--remote-host', required=True, help='Remote host to connect to')
    parser.add_argument('--remote-port', type=int, required=True, help='Remote port to connect to')
    
    args = parser.parse_args()
    
    tunnel = TCPTunnel(
        args.local_host,
        args.local_port,
        args.remote_host,
        args.remote_port
    )
    tunnel.start()

if __name__ == "__main__":
    main()
