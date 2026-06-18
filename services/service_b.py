import sys
import os
import time

# Ensure parent directory is in path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.node_simulator import NodeSimulator

def start_service():
    """Initializes and starts Service B simulator."""
    node = NodeSimulator('service_b', 'Service B')
    node.start()
    return node

if __name__ == '__main__':
    print("Starting Service B simulator in standalone mode...")
    node = start_service()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down Service B simulator...")
        node.stop()
