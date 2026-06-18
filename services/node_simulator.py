import time
import random
import threading
from database import get_db_connection
import watcher
import config_store

class NodeSimulator:
    def __init__(self, node_id, name):
        self.node_id = node_id
        self.name = name
        self.running = True
        self.thread = None

    def start(self):
        """Starts the simulator node in a background thread."""
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stops the simulator loop."""
        self.running = False

    def _get_node_state(self):
        """Reads own state from the database."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM services WHERE id = ?", (self.node_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def _update_heartbeat(self):
        """Updates own heartbeat time in the database using unix timestamp."""
        conn = get_db_connection()
        cursor = conn.cursor()
        now_ts = int(time.time())
        cursor.execute('''
            UPDATE services 
            SET last_heartbeat = ? 
            WHERE id = ?
        ''', (now_ts, self.node_id))
        conn.commit()
        conn.close()

    def _run_loop(self):
        """Main execution loop for a distributed service node."""
        watcher.log_event("SYSTEM", f"Service Node {self.name} is starting up...", "INFO")
        
        # Add randomized offset to start election checks to prevent all followers from starting election simultaneously
        time.sleep(random.uniform(0, 1.5))
        
        while self.running:
            try:
                state = self._get_node_state()
                if not state:
                    time.sleep(1)
                    continue
                
                # Check if this node is simulated as crashed (DEAD)
                if state['status'] == 'DEAD':
                    # Crashed node does not perform any activity (no heartbeat, no election, no replication)
                    time.sleep(1)
                    continue
                
                # Update heartbeat to signal this node is healthy and online
                self._update_heartbeat()
                
                role = state['role']
                term = state['term']
                current_ver = state['current_version']
                
                if role == 'LEADER':
                    self._handle_leader_role(term, current_ver)
                elif role == 'FOLLOWER':
                    self._handle_follower_role(term, current_ver)
                elif role == 'CANDIDATE':
                    self._handle_candidate_role(term)
                    
            except Exception as e:
                watcher.log_event("SYSTEM", f"Error in Node {self.name} loop: {str(e)}", "ERROR")
            
            # Sleep for 1 second before next cycle
            time.sleep(1.0)

    def _handle_leader_role(self, term, current_ver):
        """Leader actions: Heartbeat broadcasting and replication management."""
        latest_rev = config_store.get_current_revision()
        
        # If there is a new configuration update in the system, leader coordinates replication
        if latest_rev > current_ver:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Leader updates its own current version to latest
            cursor.execute("UPDATE services SET current_version = ? WHERE id = ?", (latest_rev, self.node_id))
            conn.commit()
            conn.close()
            
            watcher.log_event("REPLICATION", f"Leader {self.name} initiating replication of Revision {latest_rev}...", "INFO")
            
        # Check if quorum is met for the latest revision
        if latest_rev > 0:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as active_count FROM services WHERE current_version >= ? AND status = 'ALIVE'", (latest_rev,))
            synced_count = cursor.fetchone()['active_count']
            
            cursor.execute("SELECT COUNT(*) as total_count FROM services")
            total_count = cursor.fetchone()['total_count']
            conn.close()
            
            # Quorum requires majority: (total_count / 2) + 1
            quorum_needed = (total_count // 2) + 1
            
            # We log replication quorum achievements
            if synced_count >= quorum_needed:
                # We can broadcast a success status for configuration commit
                pass

    def _handle_follower_role(self, term, current_ver):
        """Follower actions: Monitor leader heartbeat, replicate configs."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get active leader
        cursor.execute("SELECT * FROM services WHERE role = 'LEADER'")
        leader = cursor.fetchone()
        conn.close()
        
        now = int(time.time())
        leader_timeout = False
        
        if not leader:
            leader_timeout = True
        else:
            # Check if leader is marked DEAD, or if heartbeat is older than 3 seconds
            try:
                leader_hb = int(leader['last_heartbeat'])
                if leader['status'] == 'DEAD' or (now - leader_hb) > 3:
                    leader_timeout = True
            except (ValueError, TypeError):
                leader_timeout = True
                
        if leader_timeout:
            # Leader is offline, trigger election
            leader_name = leader['name'] if leader else "None"
            watcher.log_event("ELECTION", f"Node {self.name} detected Leader {leader_name} timeout. Initiating election...", "WARNING")
            self._start_election(term)
        else:
            # Leader is healthy, update term if leader has a higher term
            if leader['term'] > term:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE services SET term = ? WHERE id = ?", (leader['term'], self.node_id))
                conn.commit()
                conn.close()
                watcher.trigger_service_update()
                
            # Replicate configuration if version is stale
            latest_rev = config_store.get_current_revision()
            if latest_rev > current_ver:
                # Simulating pull replication from database
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE services SET current_version = ? WHERE id = ?", (latest_rev, self.node_id))
                conn.commit()
                conn.close()
                watcher.log_event("REPLICATION", f"Node {self.name} replicated configuration (Revision {latest_rev}) from Leader {leader['name']}", "SUCCESS")
                watcher.trigger_service_update()

    def _start_election(self, current_term):
        """Transitions node to CANDIDATE and starts voting."""
        new_term = current_term + 1
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Transition to candidate and vote for self
        cursor.execute('''
            UPDATE services 
            SET role = 'CANDIDATE', term = ?, voted_for = ?, last_heartbeat = ?
            WHERE id = ?
        ''', (new_term, self.node_id, int(time.time()), self.node_id))
        conn.commit()
        conn.close()
        
        watcher.log_event("ELECTION", f"Node {self.name} transitioned to CANDIDATE for Term {new_term}", "INFO")
        watcher.trigger_service_update()

    def _handle_candidate_role(self, term):
        """Candidate actions: Gather votes and check for majority."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all services that are ALIVE
        cursor.execute("SELECT * FROM services WHERE status = 'ALIVE'")
        alive_nodes = cursor.fetchall()
        
        votes = 1 # Candidate votes for itself
        
        # Request votes from other alive services
        for node in alive_nodes:
            if node['id'] == self.node_id:
                continue
            
            # Simple voting logic:
            # If the node's term is less than candidate term, it grants the vote
            # Or if it has already voted for this candidate in the same term
            if node['term'] < term or (node['term'] == term and node['voted_for'] == self.node_id):
                cursor.execute('''
                    UPDATE services 
                    SET term = ?, voted_for = ? 
                    WHERE id = ?
                ''', (term, self.node_id, node['id']))
                votes += 1
                watcher.log_event("ELECTION", f"Node {node['name']} granted vote to {self.name} for Term {term}", "INFO")
                
        conn.commit()
        
        # Check if majority votes are gathered
        cursor.execute("SELECT COUNT(*) as total_count FROM services")
        total_count = cursor.fetchone()['total_count']
        conn.close()
        
        majority = (total_count // 2) + 1
        
        if votes >= majority:
            # Candidate wins! Transition to LEADER
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Demote any other leaders
            cursor.execute("UPDATE services SET role = 'FOLLOWER' WHERE role = 'LEADER'")
            # Promote self
            cursor.execute('''
                UPDATE services 
                SET role = 'LEADER', voted_for = NULL 
                WHERE id = ?
            ''', (self.node_id,))
            conn.commit()
            conn.close()
            
            watcher.log_event("ELECTION", f"Node {self.name} elected LEADER for Term {term} with {votes}/{total_count} votes!", "SUCCESS")
            watcher.trigger_service_update()
        else:
            # Failed to get majority, wait for random split-vote election timeout
            watcher.log_event("ELECTION", f"Node {self.name} failed to obtain majority votes ({votes}/{total_count}). Retrying...", "WARNING")
            # Demote self back to follower to allow re-election attempt
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE services SET role = 'FOLLOWER', voted_for = NULL WHERE id = ?", (self.node_id,))
            conn.commit()
            conn.close()
            watcher.trigger_service_update()
            
            # Random sleep to avoid repeated split votes
            time.sleep(random.uniform(1.0, 2.5))
