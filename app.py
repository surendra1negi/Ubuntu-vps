import paramiko
import socket
import threading
import requests
import logging
import os
from typing import Optional
import sys
from contextlib import contextmanager
import json
from pathlib import Path

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
        config_file: str = 'config.json',
        config_env: str = 'production'
    ):
        self.config = self._load_configuration(config_file, config_env)
        self.client = None
        self.transport = None
        self.running = False

    def _load_configuration(self, config_file: str, config_env: str) -> dict:
        """Load configuration from file and environment variables"""
        # Get server public IP
        server_ip = get_public_ip()
        if not server_ip:
            raise SSHTunnelException("Could not get server public IP")

        # Default configuration with specified values
        default_config = {
            'ssh_host': server_ip,  # Using server public IP
            'ssh_port': 22,
            'ssh_user': 'ubuntu',   # Using 'ubuntu' as default user
            'ssh_password': 'password',  # Using 'password' as default password
            'local_port': 8080,
            'remote_host': '127.0.0.1',
            'remote_port': 80,
            'timeout': 30
        }

        # Try to load from config file
        config = default_config.copy()
        config_path = Path(config_file)
        if config_path.exists():
            try:
                with open(config_path) as f:
                    file_config = json.load(f)
                    if config_env in file_config:
                        config.update(file_config[config_env])
            except Exception as e:
                logger.warning(f"Error loading config file: {e}")

        # Environment variables override config file
        env_mapping = {
            'SSH_HOST': 'ssh_host',
            'SSH_PORT': 'ssh_port',
            'SSH_USER': 'ssh_user',
            'SSH_PASSWORD': 'ssh_password',
            'LOCAL_PORT': 'local_port',
            'REMOTE_HOST': 'remote_host',
            'REMOTE_PORT': 'remote_port',
            'TUNNEL_TIMEOUT': 'timeout'
        }

        for env_var, config_key in env_mapping.items():
            env_value = os.environ.get(env_var)
            if env_value:
                try:
                    # Convert to int for port and timeout values
                    if config_key in ['ssh_port', 'local_port', 'remote_port', 'timeout']:
                        config[config_key] = int(env_value)
                    else:
                        config[config_key] = env_value
                except ValueError as e:
                    logger.error(f"Invalid environment variable {env_var}: {e}")

        # Validate configuration
        if not 1 <= config['ssh_port'] <= 65535:
            raise SSHTunnelException(f"Invalid SSH port: {config['ssh_port']}")
        
        if not 1 <= config['local_port'] <= 65535:
            raise SSHTunnelException(f"Invalid local port: {config['local_port']}")
        
        if not 1 <= config['remote_port'] <= 65535:
            raise SSHTunnelException(f"Invalid remote port: {config['remote_port']}")

        return config

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        """Start the SSH tunnel"""
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.WarningPolicy())
            
            logger.info(f"Connecting to SSH host {self.config['ssh_host']}...")
            self.client.connect(
                self.config['ssh_host'],
                port=self.config['ssh_port'],
                username=self.config['ssh_user'],
                password=self.config['ssh_password'],
                timeout=self.config['timeout'],
                allow_agent=False,
                look_for_keys=False
            )

            self.transport = self.client.get_transport()
            self.transport.request_port_forward("", self.config['local_port'])
            self.running = True

            threading.Thread(
                target=self._forward_tunnel,
                daemon=True
            ).start()

            logger.info(f"Tunnel established: http://{self.config['ssh_host']}:{self.config['local_port']}")
            
        except Exception as e:
            self.stop()
            raise SSHTunnelException(f"Failed to start SSH tunnel: {str(e)}")

    def stop(self):
        """Stop the SSH tunnel and cleanup resources"""
        self.running = False
        if self.transport:
            try:
                self.transport.cancel_port_forward("", self.config['local_port'])
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
                if self.running:
                    logger.error(f"Error in tunnel forwarding: {e}")

    def _handle_connection(self, chan):
        """Handle individual connection forwarding"""
        with create_socket() as sock:
            try:
                sock.settimeout(self.config['timeout'])
                sock.connect((self.config['remote_host'], self.config['remote_port']))
                
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
        with SSHTunnel() as tunnel:
            logger.info("Tunnel is running. Press Ctrl+C to exit.")
            while True:
                try:
                    input()
                except KeyboardInterrupt:
                    logger.info("Shutting down tunnel...")
                    break

    except SSHTunnelException as e:
        logger.error(f"Tunnel error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
