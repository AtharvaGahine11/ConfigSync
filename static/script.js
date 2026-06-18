// ==========================================================================
// ConfigSync Client-Side Controller
// Handles SSE updates, REST API operations, and DOM rendering
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const configTableBody = document.getElementById('configTableBody');
    const servicesList = document.getElementById('servicesList');
    const logConsole = document.getElementById('logConsole');
    const clearLogsBtn = document.getElementById('clearLogsBtn');
    
    // Stats Elements
    const statTotalConfigs = document.getElementById('statTotalConfigs');
    const statConnectedServices = document.getElementById('statConnectedServices');
    const statCurrentTerm = document.getElementById('statCurrentTerm');
    const statCommitLogs = document.getElementById('statCommitLogs');
    const consensusStatus = document.getElementById('consensusStatus');
    const activeLeaderHeader = document.getElementById('activeLeaderHeader');
    const globalRevisionHeader = document.getElementById('globalRevisionHeader');

    // Forms & Dialog
    const createConfigForm = document.getElementById('createConfigForm');
    const rollbackRevision = document.getElementById('rollbackRevision');
    const rollbackBtn = document.getElementById('rollbackBtn');
    const editDialog = document.getElementById('editDialog');
    const editForm = editDialog.querySelector('form');

    // State cache
    let currentConfigs = [];
    let currentServices = [];

    // --- 1. INITIAL LOAD ---
    fetchConfigs();
    fetchServices();
    initSSE();

    // --- 2. SERVER-SENT EVENTS (SSE) STREAM ---
    function initSSE() {
        const eventSource = new EventSource('/watch');

        eventSource.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                
                if (payload.type === 'ping') {
                    // Internal heartbeat check, do nothing
                    return;
                }
                
                if (payload.type === 'log') {
                    appendConsoleLog(payload.timestamp, payload.data);
                } else if (payload.type === 'config_update') {
                    fetchConfigs();
                } else if (payload.type === 'service_update') {
                    fetchServices();
                }
            } catch (e) {
                console.error("Error parsing SSE message:", e);
            }
        };

        eventSource.onerror = (err) => {
            console.error("SSE connection lost. Reconnecting...", err);
            appendConsoleLog(new Date().toLocaleTimeString(), {
                source: "SYSTEM",
                message: "Watch notification connection interrupted. Attempting to reconnect...",
                level: "WARNING"
            });
        };
    }

    // Append a log line into the console panel
    function appendConsoleLog(time, logObj) {
        const logLine = document.createElement('div');
        logLine.className = 'log-line';
        logLine.setAttribute('data-source', logObj.source || 'SYSTEM');
        logLine.setAttribute('data-level', logObj.level || 'INFO');

        const timeSpan = document.createElement('span');
        timeSpan.className = 'log-time';
        timeSpan.textContent = `[${time}] [${logObj.source}]`;

        const msgSpan = document.createElement('span');
        msgSpan.className = 'log-msg';
        msgSpan.textContent = ` ${logObj.message}`;

        logLine.appendChild(timeSpan);
        logLine.appendChild(msgSpan);
        logConsole.appendChild(logLine);

        // Auto-scroll to bottom of console
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    // --- 3. FETCH & RENDER DATA ---

    // Fetch Configurations from API
    async function fetchConfigs() {
        try {
            const response = await fetch('/configs');
            if (!response.ok) throw new Error("Failed to load configs");
            
            const configs = await response.json();
            currentConfigs = configs;
            renderConfigsTable(configs);
            
            // Update stats
            statTotalConfigs.textContent = configs.length;
        } catch (err) {
            console.error("Error fetching configs:", err);
        }
    }

    // Fetch Services from API
    async function fetchServices() {
        try {
            const response = await fetch('/services');
            if (!response.ok) throw new Error("Failed to load services");
            
            const services = await response.json();
            currentServices = services;
            renderServices(services);
            updateSystemHeader(services);
        } catch (err) {
            console.error("Error fetching services:", err);
        }
    }

    // Render configurations in table
    function renderConfigsTable(configs) {
        if (!configs || configs.length === 0) {
            configTableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-muted">No configurations found. Add one above.</td>
                </tr>
            `;
            return;
        }

        configTableBody.innerHTML = configs.map(config => `
            <tr>
                <td><code>#${config.id}</code></td>
                <td><strong>${escapeHtml(config.key)}</strong></td>
                <td><code>${escapeHtml(config.value)}</code></td>
                <td><span class="text-secondary">${escapeHtml(config.description || 'No description')}</span></td>
                <td><span class="badge badge-system">v${config.version}</span></td>
                <td class="font-mono text-muted">${config.updated_at}</td>
                <td>
                    <div class="actions-cell">
                        <button class="btn btn-outline btn-sm edit-btn" data-id="${config.id}">Edit</button>
                        <button class="btn btn-danger btn-sm delete-btn" data-id="${config.id}">Delete</button>
                    </div>
                </td>
            </tr>
        `).join('');

        // Attach action handlers
        document.querySelectorAll('.edit-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = parseInt(e.target.getAttribute('data-id'));
                openEditModal(id);
            });
        });

        document.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const id = parseInt(e.target.getAttribute('data-id'));
                deleteConfig(id);
            });
        });
    }

    // Render services list
    function renderServices(services) {
        if (!services || services.length === 0) {
            servicesList.innerHTML = `<div class="text-muted">No services registered.</div>`;
            return;
        }

        servicesList.innerHTML = services.map(node => {
            const isAlive = node.status === 'ALIVE';
            const actionText = isAlive ? 'Crash' : 'Resume';
            const actionClass = isAlive ? 'btn-danger' : 'btn-success';
            const roleClass = `role-${node.role.toLowerCase()}`;
            
            return `
                <div class="service-node">
                    <div class="node-meta">
                        <span class="node-status-dot ${isAlive ? 'alive' : 'dead'}"></span>
                        <div class="node-details">
                            <span class="node-name">${escapeHtml(node.name)}</span>
                            <span class="node-subtext">Version: v${node.current_version} | Term: ${node.term}</span>
                        </div>
                    </div>
                    
                    <div class="node-badges">
                        <span class="badge-role ${roleClass}">${node.role}</span>
                        <button class="btn btn-sm ${actionClass} toggle-node-btn" data-id="${node.id}">
                            ${actionText}
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        // Attach node control actions
        document.querySelectorAll('.toggle-node-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const node_id = e.target.getAttribute('data-id');
                toggleService(node_id);
            });
        });
    }

    // Update system header dashboard status based on services state
    async function updateSystemHeader(services) {
        const aliveCount = services.filter(s => s.status === 'ALIVE').length;
        const leaderNode = services.find(s => s.role === 'LEADER' && s.status === 'ALIVE');
        const maxTerm = Math.max(...services.map(s => s.term), 0);
        
        // Update header UI
        statConnectedServices.textContent = `${aliveCount}/${services.length}`;
        statCurrentTerm.textContent = maxTerm;
        
        if (leaderNode) {
            activeLeaderHeader.textContent = leaderNode.name;
            activeLeaderHeader.className = "status-value text-cyan";
        } else {
            activeLeaderHeader.textContent = "NO LEADER (Electing...)";
            activeLeaderHeader.className = "status-value text-danger";
        }

        if (aliveCount >= (services.length / 2) + 1) {
            consensusStatus.textContent = "Healthy (Quorum Active)";
            consensusStatus.className = "status-value text-success";
        } else {
            consensusStatus.textContent = "DEGRADED (No Quorum)";
            consensusStatus.className = "status-value text-danger";
        }

        // Fetch current global revision
        try {
            const revRes = await fetch('/history');
            if (revRes.ok) {
                const history = await revRes.json();
                const currentRev = history.length > 0 ? history[0].id : 0;
                statCommitLogs.textContent = history.length;
                globalRevisionHeader.textContent = currentRev;
                
                // Pre-fill next logical rollback suggestion
                if (history.length > 0 && !rollbackRevision.value) {
                    rollbackRevision.placeholder = `e.g. ${currentRev}`;
                }
            }
        } catch (e) {
            console.error("Error loading revision ID:", e);
        }
    }

    // --- 4. FORM AND API HANDLERS ---

    // Create configuration key-value
    createConfigForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const key = document.getElementById('createKey').value.trim();
        const value = document.getElementById('createValue').value.trim();
        const description = document.getElementById('createDescription').value.trim();

        try {
            const response = await fetch('/configs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value, description })
            });

            const result = await response.json();
            
            if (!response.ok) {
                showToast(result.error || "Failed to create configuration.", "error");
            } else {
                showToast("Configuration propagation proposed!", "success");
                createConfigForm.reset();
            }
        } catch (err) {
            console.error("API Error creating config:", err);
            showToast("Server unreachable or network error.", "error");
        }
    });

    // Delete configuration key
    async function deleteConfig(id) {
        if (!confirm("Are you sure you want to delete this configuration?")) return;

        try {
            const response = await fetch(`/configs/${id}`, { method: 'DELETE' });
            const result = await response.json();

            if (!response.ok) {
                showToast(result.error || "Failed to delete configuration.", "error");
            } else {
                showToast("Configuration deletion propagated!", "success");
            }
        } catch (err) {
            console.error("API Error deleting config:", err);
            showToast("Server unreachable or network error.", "error");
        }
    }

    // Open Edit Dialog Modal
    function openEditModal(id) {
        const config = currentConfigs.find(c => c.id === id);
        if (!config) return;

        document.getElementById('editId').value = config.id;
        document.getElementById('editKey').value = config.key;
        document.getElementById('editValue').value = config.value;
        document.getElementById('editDescription').value = config.description || '';

        editDialog.showModal();
    }

    // Edit Form submission
    editForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const id = document.getElementById('editId').value;
        const key = document.getElementById('editKey').value;
        const value = document.getElementById('editValue').value;
        const description = document.getElementById('editDescription').value;

        try {
            const response = await fetch(`/configs/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value, description })
            });

            const result = await response.json();

            if (!response.ok) {
                showToast(result.error || "Failed to update configuration.", "error");
            } else {
                showToast("Configuration update proposed!", "success");
                editDialog.close();
            }
        } catch (err) {
            console.error("API Error updating config:", err);
            showToast("Server unreachable or network error.", "error");
        }
    });

    // Toggle service state (ALIVE/DEAD)
    async function toggleService(id) {
        try {
            const response = await fetch(`/services/${id}/toggle`, { method: 'POST' });
            if (!response.ok) {
                const err = await response.json();
                showToast(err.error || "Failed to toggle service state.", "error");
            }
        } catch (e) {
            console.error("API Error toggling service:", e);
            showToast("Server unreachable.", "error");
        }
    }

    // Rollback to specific revision ID
    rollbackBtn.addEventListener('click', async () => {
        const rev = parseInt(rollbackRevision.value);
        if (!rev || rev < 1) {
            showToast("Please enter a valid positive revision number.", "error");
            return;
        }

        if (!confirm(`Are you sure you want to rollback all configurations to Revision #${rev}? This will revert configurations and write a rollback history entry.`)) {
            return;
        }

        try {
            const response = await fetch(`/rollback/${rev}`, { method: 'POST' });
            const result = await response.json();

            if (!response.ok) {
                showToast(result.error || `Failed to rollback to revision ${rev}.`, "error");
            } else {
                showToast(`System rolled back to Revision #${rev}!`, "success");
                rollbackRevision.value = '';
            }
        } catch (err) {
            console.error("API Error rolling back:", err);
            showToast("Server unreachable.", "error");
        }
    });

    // Clear logs button click
    clearLogsBtn.addEventListener('click', () => {
        logConsole.innerHTML = `
            <div class="log-line system-log">
                <span class="log-time">[SYSTEM]</span>
                <span class="log-msg">Console logs cleared. Active listeners maintain subscription.</span>
            </div>
        `;
    });

    // --- 5. NATIVE DIALOG LIGHT-DISMISS FALLBACK ---
    // If browser does not natively support backdrop dismiss via closedby="any"
    if (!('closedBy' in HTMLDialogElement.prototype)) {
        editDialog.addEventListener('click', (event) => {
            // Ignore clicks directly inside dialog elements
            if (event.target !== editDialog) return;

            const rect = editDialog.getBoundingClientRect();
            const isClickInside = (
                rect.top <= event.clientY &&
                event.clientY <= rect.top + rect.height &&
                rect.left <= event.clientX &&
                event.clientX <= rect.left + rect.width
            );

            if (!isClickInside) {
                editDialog.close();
            }
        });
    }

    // --- 6. UTILITY FUNCTIONS ---

    // Simple Toast Notifications
    function showToast(message, type = "success") {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        // CSS for Toast
        Object.assign(toast.style, {
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: '#fff',
            fontWeight: '600',
            fontSize: '0.9rem',
            zIndex: '9999',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            transform: 'translateY(100px)',
            opacity: '0',
            transition: 'all 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55)'
        });
        
        if (type === "success") {
            toast.style.backgroundColor = '#10b981';
        } else {
            toast.style.backgroundColor = '#ef4444';
        }

        document.body.appendChild(toast);
        
        // Trigger reflow & animate in
        setTimeout(() => {
            toast.style.transform = 'translateY(0)';
            toast.style.opacity = '1';
        }, 10);
        
        // Animate out & remove
        setTimeout(() => {
            toast.style.transform = 'translateY(100px)';
            toast.style.opacity = '0';
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }

    // Escape HTML tags to prevent XSS in DOM insertions
    function escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
