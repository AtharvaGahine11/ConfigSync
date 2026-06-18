import os
import json
import time
from flask import Flask, render_template, jsonify, request, Response
from database import init_db, get_db_connection
import config_store
import watcher
from services.service_a import start_service as start_a
from services.service_b import start_service as start_b
from services.service_c import start_service as start_c

app = Flask(__name__)

# Initialize database on startup
init_db()

@app.route('/')
def index():
    """Renders the main system design dashboard."""
    return render_template('index.html')

# --- CONFIGURATION REST APIs ---

@app.route('/configs', methods=['GET'])
def get_configs():
    """Retrieves all active configurations."""
    try:
        configs = config_store.get_all_configs()
        return jsonify(configs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/configs', methods=['POST'])
def create_config():
    """Creates a new configuration. Requires active consensus leader."""
    data = request.json or {}
    key = data.get('key', '').strip()
    value = data.get('value', '').strip()
    description = data.get('description', '').strip()
    
    if not key or not value:
        return jsonify({"error": "Key and Value are required fields."}), 400
        
    try:
        config_id = config_store.create_config(key, value, description)
        return jsonify({"id": config_id, "message": "Configuration created successfully."}), 201
    except config_store.WriteBlockedException as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/configs/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    """Updates an existing configuration. Requires active consensus leader."""
    data = request.json or {}
    key = data.get('key', '').strip()
    value = data.get('value', '').strip()
    description = data.get('description', '').strip()
    
    if not key or not value:
        return jsonify({"error": "Key and Value are required fields."}), 400
        
    try:
        config_store.update_config(config_id, key, value, description)
        return jsonify({"message": "Configuration updated successfully."}), 200
    except config_store.WriteBlockedException as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/configs/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    """Deletes a configuration. Requires active consensus leader."""
    try:
        config_store.delete_config(config_id)
        return jsonify({"message": "Configuration deleted successfully."}), 200
    except config_store.WriteBlockedException as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- ROLLBACK API ---

@app.route('/rollback/<int:version_id>', methods=['POST'])
def rollback(version_id):
    """Rolls back the configuration store to a specific revision."""
    try:
        config_store.rollback_to_revision(version_id)
        return jsonify({"message": f"System rolled back to revision {version_id} successfully."}), 200
    except config_store.WriteBlockedException as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- WATCH / SSE NOTIFICATION API ---

@app.route('/watch', methods=['GET'])
def watch():
    """SSE endpoint streaming live sync logs and update triggers to dashboard."""
    q = watcher.add_listener()
    
    def event_stream():
        try:
            # Initial ping to verify connection
            yield f"data: {json.dumps({'type': 'ping', 'timestamp': time.strftime('%H:%M:%S'), 'data': {}})}\n\n"
            while True:
                event_data = q.get() # blocks until event is received
                yield f"data: {event_data}\n\n"
        except GeneratorExit:
            watcher.remove_listener(q)
            
    return Response(event_stream(), mimetype='text/event-stream')

# --- SIMULATOR CONTROL & SERVICE STATUS APIs ---

@app.route('/services', methods=['GET'])
def get_services():
    """Retrieves list of active services and their Raft election status."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM services ORDER BY id ASC")
        services = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(services), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/services/<service_id>/toggle', methods=['POST'])
def toggle_service(service_id):
    """Toggles service status (crashed/running) to simulate failure scenarios."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        service = cursor.fetchone()
        
        if not service:
            conn.close()
            return jsonify({"error": f"Service {service_id} not found."}), 404
            
        new_status = 'DEAD' if service['status'] == 'ALIVE' else 'ALIVE'
        
        # If toggling to DEAD, we must clear its leadership status
        if new_status == 'DEAD':
            cursor.execute('''
                UPDATE services 
                SET status = 'DEAD', role = 'FOLLOWER', voted_for = NULL 
                WHERE id = ?
            ''', (service_id,))
            watcher.log_event("SYSTEM", f"Simulating CRASH: Service node {service['name']} is offline.", "ERROR")
        else:
            # Set heartbeat to now so it doesn't immediately time out when recovering
            cursor.execute('''
                UPDATE services 
                SET status = 'ALIVE', last_heartbeat = ?, role = 'FOLLOWER', voted_for = NULL
                WHERE id = ?
            ''', (int(time.time()), service_id))
            watcher.log_event("SYSTEM", f"Simulating RECOVERY: Service node {service['name']} is back online.", "SUCCESS")
            
        conn.commit()
        conn.close()
        
        watcher.trigger_service_update()
        return jsonify({"message": f"Service status toggled successfully.", "status": new_status}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def get_history():
    """Retrieves full config audit log history."""
    try:
        history = config_store.get_history()
        return jsonify(history), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def start_simulators():
    """Starts background simulator threads for Services A, B, and C."""
    # Prevent starting multiple instances if Flask reloader runs twice
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        watcher.log_event("SYSTEM", "Starting Service Simulators (A, B, C)...", "INFO")
        start_a()
        start_b()
        start_c()

# Run background threads
start_simulators()

if __name__ == '__main__':
    # Start Flask Webserver
    # Run with debug=True, but reloader enabled might restart background tasks twice.
    # The check inside start_simulators handles this cleanly.
    app.run(host='127.0.0.1', port=5000, debug=True)
