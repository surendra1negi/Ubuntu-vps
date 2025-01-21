import paramiko
import socket
import threading
import requests
import logging
from typing import Optional
import sys
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SSHTunnelException(Exception):
    """Custom exception for SSH tunnel errors"""
    pass

def get_public_ip() -> Optional[str]:
    """Safely retrieve public IP address"""
    try:
        response = requests.get('https://api.ipify.org', timeout=5)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Could not get public IP: {e}")
        return None

@contextmanager
def create_socket():
    """Context manager for socket creation and cleanup"""
    sock = socket.socket()
    try:
        yield sock
    finally:
        sock.close()

class SSHTunnel:
    def __init__(
        self,
        ssh_host: str,
        ssh_port: int,
        ssh_user: str,
        ssh_password: str,
        local_port: int,
        remote_host: str,
        remote_port: int,
        timeout: int = 30
    ):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.local_port = local_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.timeout = timeout
        self.client = None
        self.transport = None
        self.running = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        """Start the SSH tunnel"""
        try:
            self.client = paramiko.SSHClient()
            # Load system host keys
            self.client.load_system_host_keys()
            # More secure than AutoAddPolicy
            self.client.set_missing_host_key_policy(paramiko.WarningPolicy())
            
            logger.info(f"Connecting to SSH host {self.ssh_host}...")
            self.client.connect(
                self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                password=self.ssh_password,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False
            )

            self.transport = self.client.get_transport()
            self.transport.request_port_forward("", self.local_port)
            self.running = True

            threading.Thread(
                target=self._forward_tunnel,
                daemon=True
            ).start()

            public_ip = get_public_ip()
            if public_ip:
                logger.info(f"Tunnel established: http://{public_ip}:{self.local_port}")
            
        except Exception as e:
            self.stop()
            raise SSHTunnelException(f"Failed to start SSH tunnel: {str(e)}")

    def stop(self):
        """Stop the SSH tunnel and cleanup resources"""
        self.running = False
        if self.transport:
            try:
                self.transport.cancel_port_forward("", self.local_port)
            except Exception as e:
                logger.error(f"Error canceling port forward: {e}")
        
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                logger.error(f"Error closing SSH client: {e}")

    def _forward_tunnel(self):
        """Handle the main tunneling loop"""
        while self.running:
            try:
                chan = self.transport.accept(1000)
                if chan is None:
                    continue
                threading.Thread(
                    target=self._handle_connection,
                    args=(chan,),
                    daemon=True
                ).start()
            except Exception as e:
                if self.running:  # Only log if we're still meant to be running
                    logger.error(f"Error in tunnel forwarding: {e}")

    def _handle_connection(self, chan):
        """Handle individual connection forwarding"""
        with create_socket() as sock:
            try:
                sock.settimeout(self.timeout)
                sock.connect((self.remote_host, self.remote_port))
                
                while self.running:
                    r, w, x = socket.select([chan, sock], [], [], 1)
                    
                    if chan in r:
                        data = chan.recv(1024)
                        if not data:
                            break
                        sock.send(data)
                    
                    if sock in r:
                        data = sock.recv(1024)
                        if not data:
                            break
                        chan.send(data)
            
            except socket.timeout:
                logger.warning("Connection timed out")
            except Exception as e:
                logger.error(f"Error handling connection: {e}")
            finally:
                chan.close()

def main():
    """Main function to run the SSH tunnel"""
    try:
        # Get configuration with input validation
        ssh_host = input("Enter SSH host (IP/Domain): ").strip()
        if not ssh_host:
            raise ValueError("SSH host is required")

        ssh_port = input("Enter SSH port [22]: ").strip()
        ssh_port = int(ssh_port) if ssh_port else 22
        if not 1 <= ssh_port <= 65535:
            raise ValueError("Invalid port number")

        ssh_user = input("Enter SSH username: ").strip()
        if not ssh_user:
            raise ValueError("SSH username is required")

        ssh_password = input("Enter SSH password: ").strip()
        if not ssh_password:
            raise ValueError("SSH password is required")

        local_port = input("Enter local port for tunneling [8080]: ").strip()
        local_port = int(local_port) if local_port else 8080
        if not 1 <= local_port <= 65535:
            raise ValueError("Invalid local port")

        remote_host = input("Enter remote host [127.0.0.1]: ").strip()
        remote_host = remote_host if remote_host else "127.0.0.1"

        remote_port = input("Enter remote port [80]: ").strip()
        remote_port = int(remote_port) if remote_port else 80
        if not 1 <= remote_port <= 65535:
            raise ValueError("Invalid remote port")

        # Create and start tunnel using context manager
        with SSHTunnel(
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            local_port=local_port,
            remote_host=remote_host,
            remote_port=remote_port
        ) as tunnel:
            logger.info("Tunnel is running. Press Ctrl+C to exit.")
            while True:
                try:
                    input()
                except KeyboardInterrupt:
                    logger.info("Shutting down tunnel...")
                    break

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except SSHTunnelException as e:
        logger.error(f"Tunnel error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
