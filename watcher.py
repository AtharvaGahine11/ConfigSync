import time
import json
from queue import Queue
from threading import Lock

# List of active queues representing connected SSE clients
_listeners = []
_listeners_lock = Lock()

def add_listener():
    """Register a new SSE client listener queue."""
    q = Queue(maxsize=100)
    with _listeners_lock:
        _listeners.append(q)
    return q

def remove_listener(q):
    """Remove a disconnected SSE client listener queue."""
    with _listeners_lock:
        if q in _listeners:
            _listeners.remove(q)

def broadcast_event(event_type, data):
    """
    Broadcasts a JSON-formatted event to all registered listeners.
    event_type: 'log', 'config_update', or 'service_update'
    data: dictionary containing payload
    """
    payload = {
        "type": event_type,
        "timestamp": time.strftime("%H:%M:%S"),
        "data": data
    }
    event_str = json.dumps(payload)
    
    with _listeners_lock:
        # We make a copy of the list to iterate to avoid locking issues if listeners are added/removed
        active_listeners = list(_listeners)
        
    for q in active_listeners:
        try:
            # Non-blocking put, skip if queue is full to prevent memory leaks from slow consumers
            if q.full():
                try:
                    q.get_nowait()
                except Exception:
                    pass
            q.put_nowait(event_str)
        except Exception:
            pass

def log_event(source, message, level="INFO"):
    """
    Log an event and broadcast it to the UI console.
    source: e.g. 'ELECTION', 'REPLICATION', 'HEARTBEAT', 'SYSTEM', 'API'
    message: description of the event
    level: 'INFO', 'SUCCESS', 'WARNING', 'ERROR'
    """
    log_data = {
        "source": source,
        "message": message,
        "level": level.upper()
    }
    broadcast_event("log", log_data)
    
    # Also print to standard output for server-side terminal logs
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{source}] [{level.upper()}] {message}")

def trigger_config_update():
    """Trigger the UI to fetch the latest configurations."""
    broadcast_event("config_update", {"updated": True})

def trigger_service_update():
    """Trigger the UI to fetch the latest services state."""
    broadcast_event("service_update", {"updated": True})
