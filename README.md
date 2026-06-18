# ConfigSync – Distributed Configuration Management Service

ConfigSync is a complete, lightweight, and self-contained **Distributed Configuration Management Service** built to demonstrate core System Design concepts. Inspired by production-grade consensus engines like **Apache ZooKeeper** and **etcd**, it features a fully functional REST API, SQLite storage, version control history, point-in-time rollback, and a Raft-like leader election and configuration propagation simulator.

The project is designed to be beginner-friendly, visually interactive, and runnable locally with zero external service dependencies. It is ideal for B.Tech System Design final semester projects or practical examinations.

---

## 📖 Table of Contents
1. [Problem Statement](#-problem-statement)
2. [Key Features](#-key-features)
3. [System Architecture](#-system-architecture)
4. [Database Schema](#-database-schema)
5. [Raft-like Consensus Simulation](#-raft-like-consensus-simulation)
6. [API Documentation](#-api-documentation)
7. [Installation & Setup](#-installation--setup)
8. [Demonstration Guide](#-demonstration-guide)
9. [GitHub Upload Instructions](#-github-upload-instructions)

---

## 🚨 Problem Statement

In microservices architectures, managing application configurations (like database credentials, feature flags, API endpoints, and timeouts) dynamically across hundreds of servers is highly challenging. 

### Core Challenges:
1. **Consistency Drift**: Individual services reading configurations from static local files become out of sync during runtime updates, leading to split-brain behavior.
2. **Slow propagation**: Restarting applications to load new configurations causes service downtime and high operational latency.
3. **No Audit Trail**: Lack of configuration version control and quick rollback capabilities makes recovering from bad configuration updates slow and risky.
4. **Single Point of Failure (SPOF)**: A centralized configuration server can crash, stopping the entire system.

**ConfigSync** resolves these challenges by providing a highly available, replicated configuration store with real-time watch notifications, audit histories, consensus-driven leader elections, and point-in-time recovery rollbacks.

---

## ✨ Key Features

- **Consensus & Leader Election**: Simulates a three-node distributed cluster (Service A, B, and C) that automatically elects a leader. Handles leader heartbeat timeouts and node crashes dynamically.
- **Replication Status**: Visually tracks and verifies configuration propagation across all nodes. Displays synchronization delays and out-of-sync nodes.
- **Audit Trails & Versioning**: Maintains full change history of configurations (CREATE, UPDATE, DELETE, ROLLBACK) with auto-incrementing versions.
- **Point-in-Time Recovery**: Allows reverting the entire configuration store back to a specific global revision ID.
- **Server-Sent Events (SSE) Watcher**: Subscribes the web dashboard to server-side events, enabling instant updates of stats, tables, and logs without browser polling.
- **Interactive Control Center**: Provides buttons on the dashboard to crash/recover individual nodes to watch self-healing consensus in real-time.

---

## 🏗️ System Architecture

ConfigSync implements a modular system design:

```
[ Web Dashboard ] <---> [ Flask Backend ] <---> [ SQLite DB ]
  (HTML/CSS/JS)           (REST & SSE)           (Shared State)
                                ^
                                |
                  [ Service Nodes Simulator ]
                    (Background Threads: A, B, C)
```

- **Frontend**: A modern dark-mode user interface featuring glassmorphic stat cards, a terminal console displaying real-time events, and an interactive service manager.
- **Backend (Flask)**: Exposes APIs for CRUD configuration commands and coordinates the SSE log stream.
- **Consensus Nodes (Background Threads)**: Simulates independent processes. They use the database as a shared-state medium to coordinate Raft term elections, heartbeats, and pull-based replica catching up.

---

## 🗄️ Database Schema

We use a single SQLite file (`config.db`) containing three tables.

### 1. `configurations`
Stores the active configuration keys and values.
```sql
CREATE TABLE configurations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    version INTEGER DEFAULT 1,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2. `config_history`
Stores the changelog for point-in-time audits and recovery rollbacks.
```sql
CREATE TABLE config_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    version INTEGER NOT NULL,
    change_type TEXT NOT NULL, -- 'CREATE', 'UPDATE', 'DELETE', 'ROLLBACK'
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3. `services`
Stores node statuses, terms, heartbeats, and current version states.
```sql
CREATE TABLE services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,       -- 'LEADER', 'FOLLOWER', 'CANDIDATE'
    status TEXT NOT NULL,     -- 'ALIVE', 'DEAD'
    last_heartbeat INTEGER,   -- Unix timestamp float/int
    current_version INTEGER,  -- Replicated version ID
    term INTEGER DEFAULT 0,   -- Raft Term number
    voted_for TEXT            -- Node voted for in current election
);
```

---

## ⚙️ Raft-like Consensus Simulation

### 1. Node Heartbeat & Failure Detection
Every 1 second, all `ALIVE` nodes update their `last_heartbeat` in the database. If a follower node notices the leader's heartbeat is missing for more than 3 seconds (or if the leader is simulated as `DEAD`), it triggers a heartbeat timeout.

### 2. Leader Election
1. The timeout node changes its role to `CANDIDATE`.
2. It increments its local election `term` and votes for itself.
3. It requests votes from other `ALIVE` nodes.
4. An alive node votes for a candidate if the candidate's term is greater than its own current term.
5. If the candidate receives a majority of votes (e.g. 2 out of 3), it demotes any other leader and promotes itself to `LEADER`.

### 3. Config Propagation (Write Availability)
- Write operations (`POST`, `PUT`, `DELETE`, `ROLLBACK`) are blocked unless there is an active `LEADER` in the cluster. This demonstrates the CAP Theorem (Consistency over Availability during partitions).
- When a write succeeds on the leader, the system revision increases.
- Followers detect the version lag, pull the changes, and update their `current_version`.
- Once a quorum of alive nodes catch up to the latest revision, the leader logs a successful quorum commitment.

---

## 🔌 API Documentation

### 1. Configurations

#### `GET /configs`
Retrieves all current configurations.
- **Response (200 OK)**:
```json
[
  {
    "id": 1,
    "key": "database_url",
    "value": "postgres://localhost:5432/main",
    "description": "Production database endpoint",
    "version": 1,
    "updated_at": "2026-06-18 13:00:00"
  }
]
```

#### `POST /configs`
Proposes a new configuration.
- **Request Body**:
```json
{
  "key": "api_timeout",
  "value": "5000",
  "description": "API request timeout in milliseconds"
}
```
- **Response (201 Created)**:
```json
{
  "id": 2,
  "message": "Configuration created successfully."
}
```
- **Response (503 Service Unavailable)**: Returned if no leader is active.

#### `PUT /configs/<id>`
Updates an existing configuration. Increments key version.
- **Request Body**:
```json
{
  "key": "api_timeout",
  "value": "3000",
  "description": "Reduced timeout due to network optimization"
}
```
- **Response (200 OK)**:
```json
{
  "message": "Configuration updated successfully."
}
```

#### `DELETE /configs/<id>`
Deletes a configuration and appends a `DELETE` event to the history audit trail.
- **Response (200 OK)**:
```json
{
  "message": "Configuration deleted successfully."
}
```

### 2. Rollback

#### `POST /rollback/<version_id>`
Rolls back the entire configuration database state to the point right after revision ID `version_id` was committed.
- **Response (200 OK)**:
```json
{
  "message": "System rolled back to revision 3 successfully."
}
```

### 3. Watch Notifications

#### `GET /watch`
Server-Sent Events (SSE) stream. Establishes a persistent text event stream (`text/event-stream`) which streams real-time updates:
```
data: {"type": "log", "timestamp": "13:01:05", "data": {"source": "HEARTBEAT", "message": "Service A, B, C heartbeats verified.", "level": "INFO"}}
data: {"type": "config_update", "timestamp": "13:01:12", "data": {"updated": true}}
```

### 4. Service Simulation Controls

#### `GET /services`
Gets the status, term, role, and current version of all nodes.
- **Response (200 OK)**:
```json
[
  {
    "id": "service_a",
    "name": "Service A",
    "role": "LEADER",
    "status": "ALIVE",
    "last_heartbeat": 1776543210,
    "current_version": 2,
    "term": 1,
    "voted_for": null
  }
]
```

#### `POST /services/<service_id>/toggle`
Toggles a node between `ALIVE` and `DEAD` to simulate failures.
- **Response (200 OK)**:
```json
{
  "message": "Service status toggled successfully.",
  "status": "DEAD"
}
```

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.8+ installed.
- Modern browser (Chrome, Edge, Firefox, or Safari).

### 1. Clone & Navigate
Create your project directory and enter it:
```bash
git clone <your-repository-url> config-sync
cd config-sync
```

### 2. Install Dependencies
Install Flask from the requirements file:
```bash
pip install -r requirements.txt
```

### 3. Run the Application
Start the Flask application:
```bash
python app.py
```

### 4. View the Dashboard
Open your web browser and navigate to:
```
http://127.0.0.1:5000/
```

---

## 🧪 Demonstration Guide

Here is a step-by-step walkthrough to present this project during a viva or demonstration:

1. **Observe Startup**:
   - Notice the **Live Distributed Sync Logs** console. It will show the initial bootstrap logs, service startup, and consensus election logs.
   - Observe how a leader (e.g. Service A) gets elected in Term 1 automatically.
2. **Add a Configuration**:
   - Create a key `db_password` with value `super-secure-pass` and description.
   - Click **Propose & Propagate**.
   - Notice the log showing the API request, leader initiating replication, followers pulling the update, and quorum commit confirmations.
3. **Simulate a Crash (Leader Failure)**:
   - Identify the service node designated as `LEADER`.
   - Click the **Crash** button for that node.
   - The status dot turns **Red** (DEAD).
   - In the log terminal, notice that the remaining active followers detect the heartbeat timeout after 3 seconds.
   - Watch the election take place live: a new leader is elected with a majority term increment!
4. **Attempt Writes on partition (CAP Test)**:
   - Crash another node so only 1 node is `ALIVE`.
   - Now there is no quorum (1/3 nodes active). The header will say `DEGRADED (No Quorum)` and no leader will be elected.
   - Try to add a new configuration. The UI will toast a `503 Service Unavailable` error, showing that the system blocks write operations to prevent data inconsistency during partitions!
5. **Node Recovery & Catch-up**:
   - Resume the crashed nodes.
   - Watch the election resolve, electing a leader.
   - Notice the logs showing the recovered nodes catching up and replicating the configuration version they missed.
6. **Point-in-Time Rollback**:
   - Update a configuration multiple times to increment its version (e.g., version 2, 3, 4).
   - Look at the `Database Logs Commit` stats to identify a past revision ID.
   - Enter that ID into the **Point-in-Time Rollback** input and click **Rollback**.
   - Observe the database state roll back to that exact revision!

---



