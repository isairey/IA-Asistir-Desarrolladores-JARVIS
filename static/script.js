// Global Variables
let currentWorkspace = null;
let currentModel = null;
let pendingChanges = null;
let socket = null;
let expandedDirs = new Map(); // Track expanded directories and their pagination state
let term = null;
let fitAddon = null;
let isTerminalExpanded = false;

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initializeWebSocket();
    initializeModelSelection();
    loadWorkspaceHistory();
    initializeKeyboardShortcuts();
    initializeTerminal();
});

// Terminal Management
function initializeTerminal() {
    // Create terminal instance
    term = new Terminal({
        cursorBlink: true,
        fontSize: 14,
        fontFamily: '"Cascadia Code", "Source Code Pro", "Fira Code", Menlo, monospace',
        lineHeight: 1.3,
        letterSpacing: 0.5,
        scrollback: 5000,
        theme: {
            background: '#1e1e1e',
            foreground: '#d4d4d4',
            cursor: '#a0a0a0',
            cursorAccent: '#1e1e1e',
            selection: 'rgba(255, 255, 255, 0.15)',
            black: '#1e1e1e',
            red: '#f44747',
            green: '#6a9955',
            yellow: '#d7ba7d',
            blue: '#569cd6',
            magenta: '#c586c0',
            cyan: '#4dc9b0',
            white: '#d4d4d4',
            brightBlack: '#808080',
            brightRed: '#f44747',
            brightGreen: '#6a9955',
            brightYellow: '#d7ba7d',
            brightBlue: '#569cd6',
            brightMagenta: '#c586c0',
            brightCyan: '#4dc9b0',
            brightWhite: '#ffffff'
        },
        allowTransparency: true,
        fastScrollModifier: 'alt',
        scrollSensitivity: 2,
        rightClickSelectsWord: true,
        allowProposedApi: true
    });

    // Load addons
    fitAddon = new FitAddon.FitAddon();
    const webLinksAddon = new WebLinksAddon.WebLinksAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);

    // Open terminal in container
    term.open(document.getElementById('terminal'));
    
    // Set terminal padding
    term.element.style.padding = '8px';
    
    // Fit terminal to container
    fitAddon.fit();

    // Handle terminal input
    term.onData(data => {
        socket.emit('terminal_input', { data });
    });

    // Handle terminal resize
    window.addEventListener('resize', () => {
        fitAddon.fit();
        const dimensions = { cols: term.cols, rows: term.rows };
        socket.emit('terminal_resize', dimensions);
    });

    // Handle copy/paste
    let pasteInProgress = false;
    
    // Add paste event listener to terminal element
    term.element.addEventListener('paste', (event) => {
        event.preventDefault();
        if (!pasteInProgress) {
            pasteInProgress = true;
            const text = event.clipboardData.getData('text');
            socket.emit('terminal_input', { data: text });
            setTimeout(() => {
                pasteInProgress = false;
            }, 100);
        }
    });

    term.attachCustomKeyEventHandler((event) => {
        if (event.type === 'keydown') {
            // Copy: Ctrl+C when text is selected
            if (event.ctrlKey && !event.shiftKey && event.key === 'c' && term.hasSelection()) {
                const selectedText = term.getSelection();
                navigator.clipboard.writeText(selectedText);
                return false;
            }
            
            // Linux-style Copy: Ctrl+Shift+C
            if (event.ctrlKey && event.shiftKey && event.key === 'C') {
                const selectedText = term.getSelection();
                navigator.clipboard.writeText(selectedText);
                return false;
            }
            
            // Let the browser handle paste events natively
            if ((event.ctrlKey && !event.shiftKey && event.key === 'v') ||
                (event.ctrlKey && event.shiftKey && event.key === 'V')) {
                return false;
            }
        }
        return true;
    });

    // Initialize terminal connection
    socket.emit('terminal_init', { cols: term.cols, rows: term.rows });
}

function clearTerminal() {
    term.clear();
}

function toggleTerminal() {
    const terminalContainer = document.getElementById('terminalContainer');
    
    isTerminalExpanded = !isTerminalExpanded;
    
    if (isTerminalExpanded) {
        terminalContainer.style.height = '400px';
    } else {
        terminalContainer.style.height = '200px';
    }
    
    fitAddon.fit();
    const dimensions = { cols: term.cols, rows: term.rows };
    socket.emit('terminal_resize', dimensions);
}

// WebSocket Setup
function initializeWebSocket() {
    socket = io();
    
    // Status updates
    socket.on('status', (data) => {
        updateStatus(data.message, data.step);
    });
    
    // Progress updates
    socket.on('progress', (data) => {
        updateProgress(data.message, data.tokens);
    });
    
    // Connection status
    socket.on('connect', () => {
        console.log('Connected to server');
        updateConnectionStatus(true);
    });
    
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        updateConnectionStatus(false);
    });
    
    // Terminal events
    socket.on('terminal_output', (data) => {
        term.write(data);
    });
}

// UI Update Functions
function updateStatus(message, step) {
    const statusElement = document.getElementById('statusMessage') || createStatusElement();
    statusElement.textContent = message;
    
    // Update progress bar if exists
    const progressBar = document.getElementById('progressBar');
    if (progressBar) {
        progressBar.style.width = `${(step / 5) * 100}%`;
    }
    
    // Show error styling for negative steps
    if (step < 0) {
        statusElement.classList.add('error');
    } else {
        statusElement.classList.remove('error');
    }
    
    // Get the container element
    const container = document.getElementById('statusContainer');
    
    // Clear any existing timeout
    if (container._timeoutId) {
        clearTimeout(container._timeoutId);
    }
    
    // Set new timeout to remove the status after 10 seconds
    container._timeoutId = setTimeout(() => {
        container.remove();
    }, 10000);
}

function updateProgress(message, tokens) {
    const progressElement = document.getElementById('progressMessage') || createProgressElement();
    progressElement.textContent = message;
    
    // Get the container element
    const container = document.getElementById('progressContainer');
    
    // Clear any existing timeout
    if (container._timeoutId) {
        clearTimeout(container._timeoutId);
    }
    
    // Set new timeout to remove the progress after 10 seconds
    container._timeoutId = setTimeout(() => {
        container.remove();
    }, 10000);
}

function updateConnectionStatus(connected) {
    const statusIndicator = document.getElementById('connectionStatus') || createConnectionIndicator();
    statusIndicator.className = `connection-status ${connected ? 'connected' : 'disconnected'}`;
    statusIndicator.title = connected ? 'Connected to server' : 'Disconnected from server';
}

// UI Element Creation
function createStatusElement() {
    const container = document.createElement('div');
    container.id = 'statusContainer';
    container.className = 'status-container fixed bottom-4 right-4 p-4 bg-gray-800 rounded-lg shadow-lg z-50';
    
    const message = document.createElement('div');
    message.id = 'statusMessage';
    message.className = 'text-white';
    
    const progress = document.createElement('div');
    progress.className = 'mt-2 h-2 bg-gray-700 rounded-full overflow-hidden';
    
    const bar = document.createElement('div');
    bar.id = 'progressBar';
    bar.className = 'h-full bg-blue-500 transition-all duration-300';
    bar.style.width = '0%';
    
    progress.appendChild(bar);
    container.appendChild(message);
    container.appendChild(progress);
    document.body.appendChild(container);
    
    return message;
}

function createProgressElement() {
    const container = document.createElement('div');
    container.id = 'progressContainer';
    container.className = 'progress-container fixed bottom-24 right-4 p-4 bg-gray-800 rounded-lg shadow-lg z-50';
    
    const message = document.createElement('div');
    message.id = 'progressMessage';
    message.className = 'text-white';
    
    container.appendChild(message);
    document.body.appendChild(container);
    
    return message;
}

function createConnectionIndicator() {
    const indicator = document.createElement('div');
    indicator.id = 'connectionStatus';
    indicator.className = 'connection-status';
    indicator.style.cssText = `
        position: fixed;
        top: 1rem;
        right: 1rem;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        z-index: 100;
    `;
    
    const style = document.createElement('style');
    style.textContent = `
        .connection-status.connected { background-color: #10B981; }
        .connection-status.disconnected { background-color: #EF4444; }
    `;
    document.head.appendChild(style);
    document.body.appendChild(indicator);
    
    return indicator;
}

// Model Selection
function initializeModelSelection() {
    const modelSelect = document.getElementById('modelSelect');
    modelSelect.addEventListener('change', (e) => {
        currentModel = e.target.value;
    });
    loadAvailableModels();
}

async function loadAvailableModels() {
    try {
        const response = await fetch('/models');
        const data = await response.json();

        if (data.status === 'success') {
            const modelSelect = document.getElementById('modelSelect');
            modelSelect.innerHTML = '';

            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.name;
                modelSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading models:', error);
    }
}

// Mode Switching
function setMode(mode) {
    const codeMode = document.getElementById('codeMode');
    const chatMode = document.getElementById('chatMode');
    const codeModeBtn = document.querySelector('[onclick="setMode(\'code\')"]');
    const chatModeBtn = document.querySelector('[onclick="setMode(\'chat\')"]');

    if (mode === 'code') {
        codeMode.classList.remove('hidden');
        chatMode.classList.add('hidden');
        codeModeBtn.classList.add('active');
        chatModeBtn.classList.remove('active');
    } else {
        chatMode.classList.remove('hidden');
        codeMode.classList.add('hidden');
        chatModeBtn.classList.add('active');
        codeModeBtn.classList.remove('active');
    }
}

// Workspace Management
async function createWorkspace() {
    showLoading();
    try {
        const response = await fetch('/workspace/create', { method: 'POST' });
        const data = await response.json();

        if (data.status === 'success') {
            currentWorkspace = data.workspace_dir;
            updateWorkspaceInfo(data.workspace_id);
            updateWorkspaceTree(data.structure);
            await loadWorkspaceHistory();
        } else {
            showError('Failed to create workspace');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Failed to create workspace: ' + error.message);
    } finally {
        hideLoading();
    }
}

async function loadWorkspaceHistory() {
    try {
        console.log('Loading workspace history');
        const response = await fetch('/workspace/history');
        const data = await response.json();
        console.log('Workspace history response:', data);

        if (data.status === 'success') {
            const historyList = document.getElementById('workspaceHistory');
            historyList.innerHTML = '';

            data.history.forEach(workspace => {
                console.log('Creating workspace item:', workspace);
                const workspaceDiv = document.createElement('div');
                const isImported = workspace.is_imported;
                workspaceDiv.className = `workspace-item flex items-center justify-between p-3 hover:bg-gray-700 rounded-lg cursor-pointer transition-colors ${isImported ? 'border-l-4 border-blue-500 bg-blue-900 bg-opacity-10' : ''} ${workspace.path === currentWorkspace ? 'bg-blue-900 bg-opacity-20' : ''}`;
                workspaceDiv.dataset.path = workspace.path;
                console.log('Set workspace path:', workspaceDiv.dataset.path);
                
                // Make the entire div clickable
                workspaceDiv.onclick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('Workspace clicked:', workspace.path);
                    selectWorkspace(workspace.path);
                };
                
                const infoDiv = document.createElement('div');
                infoDiv.className = 'flex-1';
                
                const nameSpan = document.createElement('div');
                nameSpan.className = 'flex items-center gap-2';
                nameSpan.innerHTML = `
                    <i class="fas fa-${isImported ? 'link' : 'folder'} ${isImported ? 'text-blue-400' : 'text-gray-400'}"></i>
                    <span class="font-medium">${workspace.id}</span>
                    ${isImported ? '<span class="text-xs text-blue-400">(Imported)</span>' : ''}
                `;
                
                const statsSpan = document.createElement('span');
                statsSpan.className = 'text-sm text-gray-400 block mt-1';
                statsSpan.textContent = `${workspace.file_count} files`;
                
                infoDiv.appendChild(nameSpan);
                infoDiv.appendChild(statsSpan);
                
                const actionsDiv = document.createElement('div');
                actionsDiv.className = 'flex items-center gap-2';
                
                if (isImported) {
                    // Show Unlink button for imported workspaces
                    const unlinkBtn = document.createElement('button');
                    unlinkBtn.className = 'p-2 text-red-400 hover:text-red-300 transition-colors';
                    unlinkBtn.innerHTML = '<i class="fas fa-unlink"></i>';
                    unlinkBtn.title = 'Unlink workspace';
                    unlinkBtn.onclick = (e) => {
                        e.stopPropagation();
                        if (confirm('Are you sure you want to unlink this workspace? The original folder will remain unchanged.')) {
                            deleteWorkspace(workspace.id);
                        }
                    };
                    actionsDiv.appendChild(unlinkBtn);
                } else {
                    // Show Rename and Delete buttons for regular workspaces
                    const renameBtn = document.createElement('button');
                    renameBtn.className = 'p-2 text-blue-400 hover:text-blue-300 transition-colors';
                    renameBtn.innerHTML = '<i class="fas fa-edit"></i>';
                    renameBtn.title = 'Rename workspace';
                    renameBtn.onclick = (e) => {
                        e.stopPropagation();
                        const newName = prompt('Enter new workspace name:', workspace.id);
                        if (newName && newName !== workspace.id) {
                            renameWorkspace(workspace.id, newName);
                        }
                    };
                    
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'p-2 text-red-400 hover:text-red-300 transition-colors';
                    deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
                    deleteBtn.title = 'Delete workspace';
                    deleteBtn.onclick = (e) => {
                        e.stopPropagation();
                        if (confirm('Are you sure you want to delete this workspace? This action cannot be undone.')) {
                            deleteWorkspace(workspace.id);
                        }
                    };
                    
                    actionsDiv.appendChild(renameBtn);
                    actionsDiv.appendChild(deleteBtn);
                }
                
                workspaceDiv.appendChild(infoDiv);
                workspaceDiv.appendChild(actionsDiv);
                historyList.appendChild(workspaceDiv);
            });
        }
    } catch (error) {
        console.error('Error loading history:', error);
        showError('Failed to load workspace history');
    }
}

async function deleteWorkspace(workspaceId) {
    try {
        const response = await fetch('/workspace/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_id: workspaceId })
        });

        const data = await response.json();
        
        if (data.status === 'success') {
            // If the deleted workspace was the current one, clear it
            if (currentWorkspace && currentWorkspace.endsWith(workspaceId)) {
                currentWorkspace = null;
                document.getElementById('currentWorkspaceInfo').classList.add('hidden');
                document.getElementById('workspaceTree').innerHTML = '';
            }
            
            // Reload the workspace history
            loadWorkspaceHistory();
        } else {
            showError(data.message || 'Failed to delete workspace');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Failed to delete workspace: ' + error.message);
    }
}

async function renameWorkspace(workspaceId, newName) {
    try {
        const response = await fetch('/workspace/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workspace_id: workspaceId,
                new_name: newName
            })
        });

        const data = await response.json();
        
        if (data.status === 'success') {
            // If the renamed workspace was the current one, update it
            if (currentWorkspace && currentWorkspace.endsWith(workspaceId)) {
                currentWorkspace = data.new_path;
                updateWorkspaceInfo(newName);
            }
            
            // Reload the workspace history
            loadWorkspaceHistory();
        } else {
            showError(data.message || 'Failed to rename workspace');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Failed to rename workspace: ' + error.message);
    }
}

function createButton(iconClass, buttonClass, onClick) {
    const button = document.createElement('button');
    button.className = buttonClass + ' transition-colors';
    button.innerHTML = `<i class="${iconClass}"></i>`;
    button.onclick = (e) => {
        e.stopPropagation();
        onClick();
    };
    return button;
}

async function selectWorkspace(path) {
    console.log('Selecting workspace:', path);
    
    // Clear previous selection
    document.querySelectorAll('.workspace-item').forEach(item => {
        item.classList.remove('bg-blue-900', 'bg-opacity-20');
    });
    
    // Find and highlight the selected workspace
    const selectedItem = Array.from(document.querySelectorAll('.workspace-item')).find(
        item => item.dataset.path === path
    );
    console.log('Found selected item:', selectedItem);
    if (selectedItem) {
        selectedItem.classList.add('bg-blue-900', 'bg-opacity-20');
    }

    currentWorkspace = path;
    console.log('Current workspace set to:', currentWorkspace);
    
    try {
        console.log('Fetching workspace structure for:', path);
        const response = await fetch('/workspace/structure', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_dir: path })
        });
        
        const data = await response.json();
        console.log('Workspace structure response:', data);
        
        if (data.status === 'success') {
            // Update workspace info
            const workspaceInfo = document.getElementById('currentWorkspaceInfo');
            if (workspaceInfo) {
                workspaceInfo.classList.remove('hidden');
            }
            
            const workspaceName = document.getElementById('currentWorkspaceName');
            if (workspaceName) {
                workspaceName.textContent = path.split('/').pop();
            }
            
            // Update tree structure
            const workspaceTree = document.getElementById('workspaceTree');
            if (workspaceTree) {
                workspaceTree.innerHTML = '';
                buildTree(data.structure, workspaceTree);
            }

            // Send terminal command to change directory
            if (socket) {
                socket.emit('terminal_input', { data: `cd "${path}"\n` });
            }
        } else {
            showError('Failed to load workspace structure');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Failed to load workspace structure: ' + error.message);
    }
}

function updateWorkspaceInfo(id) {
    currentWorkspace = id;
    const workspaceInfo = document.getElementById('currentWorkspaceInfo');
    const workspaceName = document.getElementById('currentWorkspaceName');
    
    if (workspaceInfo) {
        workspaceInfo.classList.remove('hidden');
    }
    
    if (workspaceName) {
        workspaceName.textContent = id;
    }
}

// File Tree Management
async function expandDirectory(dirElement, path) {
    const isExpanded = dirElement.getAttribute('aria-expanded') === 'true';
    const childrenContainer = dirElement.nextElementSibling;
    
    if (isExpanded) {
        // Collapse directory
        dirElement.setAttribute('aria-expanded', 'false');
        childrenContainer.innerHTML = '';
        expandedDirs.delete(path);
        return;
    }
    
    // Expand directory
    dirElement.setAttribute('aria-expanded', 'true');
    
    try {
        // Get or initialize pagination state
        let paginationState = expandedDirs.get(path) || { page: 1, hasMore: true, loading: false };
        if (paginationState.loading) return;
        
        paginationState.loading = true;
        expandedDirs.set(path, paginationState);
        
        const response = await fetch('/workspace/expand', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workspace_dir: currentWorkspace,
                dir_path: path,
                page: paginationState.page,
                page_size: 100
            })
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            // Create or get the children container
            if (!childrenContainer) {
                const newContainer = document.createElement('div');
                newContainer.className = 'pl-4';
                dirElement.parentNode.insertBefore(newContainer, dirElement.nextSibling);
            }
            
            // Append new items
            data.items.forEach(item => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'flex items-center py-1';
                
                if (item.type === 'directory') {
                    itemDiv.innerHTML = `
                        <div class="flex items-center cursor-pointer hover:text-blue-400 w-full" 
                             onclick="expandDirectory(this, '${item.path}')"
                             aria-expanded="false">
                            <i class="fas fa-folder mr-2 text-gray-400"></i>
                            <span class="truncate">${item.path.split('/').pop()}</span>
                        </div>
                    `;
                } else {
                    itemDiv.innerHTML = `
                        <div class="flex items-center cursor-pointer hover:text-blue-400 w-full"
                             onclick="selectFile('${item.path}')">
                            <i class="fas fa-file mr-2 text-gray-400"></i>
                            <span class="truncate">${item.path.split('/').pop()}</span>
                        </div>
                    `;
                }
                
                childrenContainer.appendChild(itemDiv);
            });
            
            // Update pagination state
            paginationState.hasMore = data.has_more;
            paginationState.page++;
            paginationState.loading = false;
            expandedDirs.set(path, paginationState);
            
            // Add "Load More" button if there are more items
            if (data.has_more) {
                const loadMoreDiv = document.createElement('div');
                loadMoreDiv.className = 'text-center py-2';
                loadMoreDiv.innerHTML = `
                    <button class="text-sm text-blue-400 hover:text-blue-300"
                            onclick="loadMoreItems('${path}')">
                        Load More...
                    </button>
                `;
                childrenContainer.appendChild(loadMoreDiv);
            }
        }
    } catch (error) {
        console.error('Error expanding directory:', error);
        showError('Failed to expand directory: ' + error.message);
    }
}

async function loadMoreItems(path) {
    const paginationState = expandedDirs.get(path);
    if (!paginationState || paginationState.loading || !paginationState.hasMore) return;
    
    // Find the directory element and its children container
    const dirElement = Array.from(document.querySelectorAll('[aria-expanded="true"]'))
        .find(el => el.querySelector('span').textContent === path.split('/').pop());
    
    if (dirElement) {
        const childrenContainer = dirElement.nextElementSibling;
        // Remove the existing "Load More" button
        const loadMoreButton = childrenContainer.querySelector('button');
        if (loadMoreButton) {
            loadMoreButton.parentElement.remove();
        }
        
        // Load the next page
        await expandDirectory(dirElement, path);
    }
}

function updateWorkspaceTree(structure) {
    const workspaceTree = document.getElementById('workspaceTree');
    if (workspaceTree) {
        workspaceTree.innerHTML = '';
        expandedDirs.clear(); // Reset expanded directories state
        buildTree(structure, workspaceTree);
    }
}

function buildTree(structure, container, parentPath = '') {
    structure.forEach(item => {
        const itemDiv = document.createElement('div');
        itemDiv.className = `tree-item ${item.type === 'directory' ? 'folder' : 'file'}`;
        
        // Construct the full path by combining parent path with current item path
        const itemPath = item.path;
        const fullPath = parentPath ? `${parentPath}/${itemPath}` : itemPath;
        
        if (item.type === 'directory') {
            const folderHeader = document.createElement('div');
            folderHeader.className = 'folder-header flex items-center gap-2 p-1 hover:bg-gray-700 rounded cursor-pointer';
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-folder text-yellow-400';
            folderHeader.appendChild(icon);
            
            const name = document.createElement('span');
            name.className = 'name text-gray-300';
            name.textContent = itemPath.split('/').pop();
            folderHeader.appendChild(name);
            
            // Add code generation button
            const codeGenBtn = document.createElement('button');
            codeGenBtn.className = 'code-gen-btn';
            codeGenBtn.innerHTML = '<i class="fas fa-code"></i>';
            codeGenBtn.title = 'Get Code Insights';
            codeGenBtn.onclick = (e) => {
                e.stopPropagation();
                getCodeGeneration(fullPath, 'directory');
            };
            folderHeader.appendChild(codeGenBtn);
            
            // Add recommendation button
            const recBtn = document.createElement('button');
            recBtn.className = 'recommendation-btn';
            recBtn.innerHTML = '<i class="fas fa-brain"></i>';
            recBtn.title = 'Get AI Insights';
            recBtn.onclick = (e) => {
                e.stopPropagation();
                getRecommendations(fullPath, 'directory');
            };
            folderHeader.appendChild(recBtn);
            
            itemDiv.appendChild(folderHeader);
            
            const children = document.createElement('div');
            children.className = 'children';
            itemDiv.appendChild(children);
            
            // Store the full path as a data attribute
            folderHeader.dataset.path = fullPath;
            
            // Handle folder click for expanding/collapsing
            folderHeader.onclick = async (e) => {
                e.stopPropagation();
                
                // Toggle expanded state
                itemDiv.classList.toggle('expanded');
                icon.className = itemDiv.classList.contains('expanded') ? 
                    'fas fa-folder-open text-yellow-400' : 
                    'fas fa-folder text-yellow-400';

                // Debug logs
                console.log('Folder clicked:', {
                    fullPath: fullPath,
                    isExpanded: itemDiv.classList.contains('expanded'),
                    hasChildren: item.has_children,
                    currentChildren: children.hasChildNodes(),
                    workspace: currentWorkspace
                });
                
                // Only fetch if we're expanding and there are no children yet
                if (itemDiv.classList.contains('expanded') && !children.hasChildNodes() && item.has_children) {
                    try {
                        children.innerHTML = '<div class="text-gray-400 pl-4"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
                        
                        const requestData = {
                            workspace_dir: currentWorkspace,
                            dir_path: fullPath,  // Use the full path here
                            page: 1,
                            page_size: 100
                        };
                        
                        console.log('Sending request to expand folder:', requestData);
                        
                        const response = await fetch('/workspace/expand', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(requestData)
                        });
                        
                        const data = await response.json();
                        console.log('Raw server response:', data);
                        
                        if (response.ok && data.status === 'success') {
                            children.innerHTML = '';
                            
                            // Validate response data
                            if (!data.items) {
                                console.error('No items array in response:', data);
                                throw new Error('Invalid response format: missing items array');
                            }
                            
                            if (!Array.isArray(data.items)) {
                                console.error('Items is not an array:', data.items);
                                throw new Error('Invalid response format: items is not an array');
                            }
                            
                            if (data.items.length > 0) {
                                console.log('Processing items:', data.items);
                                
                                // Validate each item
                                data.items.forEach((item, index) => {
                                    if (!item.type || !item.path) {
                                        console.error(`Invalid item at index ${index}:`, item);
                                        throw new Error(`Invalid item format at index ${index}`);
                                    }
                                });
                                
                                // Pass the current full path as parent path for nested items
                                buildTree(data.items, children, fullPath);
                                
                                // Add "Load More" button if there are more items
                                if (data.has_more) {
                                    const loadMoreDiv = document.createElement('div');
                                    loadMoreDiv.className = 'text-center py-2';
                                    loadMoreDiv.innerHTML = `
                                        <button class="text-sm text-blue-400 hover:text-blue-300"
                                                onclick="loadMoreItems('${fullPath}')">
                                            Load More (${data.total_items - data.items.length} more)
                                        </button>
                                    `;
                                    children.appendChild(loadMoreDiv);
                                }
                                
                                console.log('Successfully built tree with', data.items.length, 'items');
                            } else {
                                console.log('Folder is empty');
                                children.innerHTML = '<div class="text-gray-400 pl-4">Empty folder</div>';
                            }
                        } else {
                            console.error('Server error response:', data);
                            throw new Error(data.message || 'Failed to load folder contents');
                        }
                    } catch (error) {
                        console.error('Error in folder expansion:', error);
                        children.innerHTML = `<div class="text-red-400 pl-4">Error: ${error.message}</div>`;
                        // On error, collapse the folder
                        itemDiv.classList.remove('expanded');
                        icon.className = 'fas fa-folder text-yellow-400';
                        
                        // Show error notification
                        showError(`Failed to load folder contents: ${error.message}`);
                    }
                }
            };
        } else {
            const fileHeader = document.createElement('div');
            fileHeader.className = 'file-header flex items-center gap-2 p-1 hover:bg-gray-700 rounded cursor-pointer';
            
            const icon = document.createElement('i');
            const iconClass = getFileIcon(itemPath);
            icon.className = `fas ${iconClass}`;
            fileHeader.appendChild(icon);
            
            const name = document.createElement('span');
            name.className = 'name text-gray-300';
            name.textContent = itemPath.split('/').pop();
            fileHeader.appendChild(name);
            
            // Add code generation button
            const codeGenBtn = document.createElement('button');
            codeGenBtn.className = 'code-gen-btn';
            codeGenBtn.innerHTML = '<i class="fas fa-code"></i>';
            codeGenBtn.title = 'Get Code Insights';
            codeGenBtn.onclick = (e) => {
                e.stopPropagation();
                getCodeGeneration(fullPath, 'file');
            };
            fileHeader.appendChild(codeGenBtn);
            
            // Add recommendation button
            const recBtn = document.createElement('button');
            recBtn.className = 'recommendation-btn';
            recBtn.innerHTML = '<i class="fas fa-brain"></i>';
            recBtn.title = 'Get AI insights';
            recBtn.onclick = (e) => {
                e.stopPropagation();
                getRecommendations(fullPath, 'file');
            };
            fileHeader.appendChild(recBtn);
            
            // Show file size for large files
            if (item.size > 1024 * 1024) { // 1MB
                const size = document.createElement('span');
                size.className = 'text-xs text-gray-400 ml-2';
                size.textContent = `${(item.size / (1024 * 1024)).toFixed(1)}MB`;
                fileHeader.appendChild(size);
            }
            
            itemDiv.appendChild(fileHeader);
            
            // Store the full path as a data attribute
            fileHeader.dataset.path = fullPath;
            
            // Add click handler to view file content
            fileHeader.onclick = (e) => {
                e.stopPropagation();
                showFileContent(fullPath);
            };
        }
        
        container.appendChild(itemDiv);
    });
}

function getFileIcon(path) {
    const ext = path.split('.').pop().toLowerCase();
    const filename = path.split('/').pop().toLowerCase();
    
    // First check for specific filenames
    const filenameIcons = {
        // Docker
        'dockerfile': 'fa-brands fa-docker',
        'docker-compose.yml': 'fa-brands fa-docker',
        'docker-compose.yaml': 'fa-brands fa-docker',
        '.dockerignore': 'fa-brands fa-docker',
        
        // Git
        '.gitignore': 'fa-brands fa-git-alt',
        '.gitattributes': 'fa-brands fa-git-alt',
        '.gitmodules': 'fa-brands fa-git-alt',
        
        // Environment & Config
        '.env': 'fa-solid fa-lock',
        '.env.example': 'fa-solid fa-lock',
        '.env.local': 'fa-solid fa-lock',
        '.env.development': 'fa-solid fa-lock',
        '.env.production': 'fa-solid fa-lock',
        'config.json': 'fa-solid fa-cog',
        'config.js': 'fa-solid fa-cog',
        'config.yml': 'fa-solid fa-cog',
        'config.yaml': 'fa-solid fa-cog',
        
        // Package Management
        'package.json': 'fa-brands fa-npm',
        'package-lock.json': 'fa-brands fa-npm',
        'composer.json': 'fa-brands fa-php',
        'composer.lock': 'fa-brands fa-php',
        'requirements.txt': 'fa-brands fa-python',
        'pipfile': 'fa-brands fa-python',
        'pipfile.lock': 'fa-brands fa-python',
        'cargo.toml': 'fa-solid fa-cube',
        'cargo.lock': 'fa-solid fa-cube',
        
        // Documentation
        'readme.md': 'fa-solid fa-book',
        'changelog.md': 'fa-solid fa-list',
        'license': 'fa-solid fa-certificate',
        'license.md': 'fa-solid fa-certificate',
        'license.txt': 'fa-solid fa-certificate',
        
        // Build & Config
        'makefile': 'fa-solid fa-cogs',
        '.travis.yml': 'fa-solid fa-cog',
        '.gitlab-ci.yml': 'fa-brands fa-gitlab',
        'jenkins': 'fa-solid fa-cog',
        'webpack.config.js': 'fa-solid fa-cog',
        'tsconfig.json': 'fa-solid fa-cog'
    };

    if (filenameIcons[filename]) {
        return filenameIcons[filename];
    }

    // Then check file extensions
    const extensionIcons = {
        // Web Development
        'html': 'fa-brands fa-html5',
        'htm': 'fa-brands fa-html5',
        'css': 'fa-brands fa-css3-alt',
        'scss': 'fa-brands fa-sass',
        'sass': 'fa-brands fa-sass',
        'less': 'fa-brands fa-less',
        'js': 'fa-brands fa-js',
        'jsx': 'fa-brands fa-react',
        'ts': 'fa-solid fa-code',
        'tsx': 'fa-brands fa-react',
        'vue': 'fa-brands fa-vuejs',
        'php': 'fa-brands fa-php',
        'py': 'fa-brands fa-python',
        'rb': 'fa-solid fa-gem',
        'java': 'fa-brands fa-java',
        'go': 'fa-solid fa-code',
        'rs': 'fa-solid fa-code',
        'swift': 'fa-solid fa-code',
        'kt': 'fa-solid fa-code',
        
        // Documents
        'md': 'fa-solid fa-file-lines',
        'txt': 'fa-solid fa-file-lines',
        'pdf': 'fa-solid fa-file-pdf',
        'doc': 'fa-solid fa-file-word',
        'docx': 'fa-solid fa-file-word',
        'xls': 'fa-solid fa-file-excel',
        'xlsx': 'fa-solid fa-file-excel',
        'ppt': 'fa-solid fa-file-powerpoint',
        'pptx': 'fa-solid fa-file-powerpoint',
        
        // Images
        'jpg': 'fa-solid fa-file-image',
        'jpeg': 'fa-solid fa-file-image',
        'png': 'fa-solid fa-file-image',
        'gif': 'fa-solid fa-file-image',
        'svg': 'fa-solid fa-file-image',
        'webp': 'fa-solid fa-file-image',
        
        // Audio & Video
        'mp3': 'fa-solid fa-file-audio',
        'wav': 'fa-solid fa-file-audio',
        'ogg': 'fa-solid fa-file-audio',
        'mp4': 'fa-solid fa-file-video',
        'avi': 'fa-solid fa-file-video',
        'mov': 'fa-solid fa-file-video',
        'webm': 'fa-solid fa-file-video',
        
        // Archives
        'zip': 'fa-solid fa-file-archive',
        'rar': 'fa-solid fa-file-archive',
        '7z': 'fa-solid fa-file-archive',
        'tar': 'fa-solid fa-file-archive',
        'gz': 'fa-solid fa-file-archive',
        
        // Data & Config
        'json': 'fa-solid fa-code',
        'yaml': 'fa-solid fa-code',
        'yml': 'fa-solid fa-code',
        'xml': 'fa-solid fa-code',
        'sql': 'fa-solid fa-database',
        'db': 'fa-solid fa-database',
        'sqlite': 'fa-solid fa-database',
        
        // Shell Scripts
        'sh': 'fa-solid fa-terminal',
        'bash': 'fa-solid fa-terminal',
        'zsh': 'fa-solid fa-terminal',
        'fish': 'fa-solid fa-terminal',
        'ps1': 'fa-solid fa-terminal',
        'bat': 'fa-solid fa-terminal',
        'cmd': 'fa-solid fa-terminal',
        
        // Other
        'log': 'fa-solid fa-file-lines',
        'key': 'fa-solid fa-key',
        'pem': 'fa-solid fa-key',
        'crt': 'fa-solid fa-certificate',
        'cer': 'fa-solid fa-certificate'
    };

    return extensionIcons[ext] || 'fa-solid fa-file-code';
}

// Code Generation
async function processPrompt() {
    if (!validateWorkspace()) return;

    const promptInput = document.getElementById('promptInput');
    const prompt = promptInput.value.trim();
    
    if (!prompt) {
        showError('Please enter a prompt');
        return;
    }

    // Collect attachments
    const attachments = [];
    document.querySelectorAll('#codeAttachments > div').forEach(div => {
        attachments.push({
            name: div.querySelector('span').textContent,
            content: div.dataset.content // Get the stored file content
        });
    });

    showLoading();
    try {
        // Extract context path from the prompt if it contains a file/folder path
        let contextPath = null;
        const pathMatch = prompt.match(/(?:folder|file) "([^"]+)"/);
        if (pathMatch) {
            contextPath = pathMatch[1];
        }

        const response = await fetch('/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                prompt: prompt,
                workspace_dir: currentWorkspace,
                model_id: document.getElementById('modelSelect').value,
                attachments: attachments,
                context_path: contextPath  // Add the context path if available
            })
        });

        const data = await response.json();
        
        if (data.status === 'error') {
            showError(data.message || 'No changes to apply');
            return;
        }

        currentWorkspace = data.workspace_dir;
        if (data.structure) {
            updateWorkspaceTree(data.structure);
        }
        if (data.requires_approval) {
            showApprovalModal(data);
        }

    } catch (error) {
        console.error('Error:', error);
        showError('Failed to process prompt: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Chat Functionality
async function sendChatMessage() {
    if (!validateWorkspace()) return;

    const chatInput = document.getElementById('chatInput');
    const message = chatInput.value.trim();
    
    if (!message) {
        showError('Please enter a message');
        return;
    }

    // Collect attachments
    const attachments = [];
    document.querySelectorAll('#chatAttachments > div').forEach(div => {
        attachments.push({
            name: div.querySelector('span').textContent,
            content: div.dataset.content // Get the stored file content
        });
    });

    // Append user message first
    appendChatMessage(message, 'user');
    chatInput.value = '';

    // Show loading indicator
    const loadingMessage = appendChatMessage('<i class="fas fa-spinner fa-spin"></i> Thinking...', 'assistant', true);
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                prompt: message,
                workspace_dir: currentWorkspace,
                model_id: document.getElementById('modelSelect').value,
                attachments: attachments
            })
        });

        const data = await response.json();
        
        // Remove loading message
        loadingMessage.remove();

        if (data.status === 'success') {
            const formattedResponse = formatChatResponse(data.response);
            appendChatMessage(formattedResponse, 'assistant', true);
        } else {
            appendErrorMessage(data.message || 'Failed to get response');
        }
    } catch (error) {
        console.error('Error:', error);
        loadingMessage.remove();
        appendErrorMessage('Error: ' + error.message);
    }
}

function clearChatHistory() {
    if (confirm('Are you sure you want to clear the chat history?')) {
        const chatHistory = document.getElementById('chatHistory');
        if (chatHistory) {
            chatHistory.innerHTML = '';
            // Add a system message to indicate the chat was cleared
            appendChatMessage('Chat history has been cleared.', 'assistant', true);
        }
    }
}

function formatChatResponse(text) {
    // Configure marked options for GitHub-like rendering
    marked.setOptions({
        gfm: true,                // GitHub Flavored Markdown
        breaks: true,             // Add <br> on single line breaks
        headerIds: true,          // Add ids to headers
        mangle: false,            // Don't escape header IDs
        pedantic: false,          // Don't be too strict
        smartLists: true,         // Use smarter list behavior
        smartypants: true,        // Use smart punctuation
        highlight: function(code, lang) {
            // Add syntax highlighting classes
            if (lang && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(code, { language: lang }).value;
                } catch (err) {}
            }
            return code;
        }
    });

    // Split text into code blocks and regular text
    const parts = text.split('```');
    const formattedParts = [];
    
    for (let i = 0; i < parts.length; i++) {
        if (i % 2 === 0) {
            // Regular text: convert markdown to HTML
            let regularText = parts[i].trim();
            if (regularText) {
                regularText = marked.parse(regularText);
                formattedParts.push(regularText);
            }
        } else {
            // Code block: preserve formatting and add syntax highlighting
            let code = parts[i];
            let language = '';
            
            // Check if language is specified
            const firstLineBreak = code.indexOf('\n');
            if (firstLineBreak !== -1) {
                language = code.substring(0, firstLineBreak).trim();
                code = code.substring(firstLineBreak + 1);
            }
            
            // Clean up code
            code = code.trim()
                .replace(/\n\s*\n/g, '\n')  // Remove empty lines
                .replace(/[ \t]+$/gm, '')   // Remove trailing spaces
                .replace(/^\s+|\s+$/g, ''); // Remove leading/trailing spaces
            
            // Escape HTML entities
            code = code
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');

            // Apply syntax highlighting if language is specified
            if (language && hljs.getLanguage(language)) {
                try {
                    code = hljs.highlight(code, { language: language }).value;
                } catch (err) {}
            }

            // Create code block with language label
            formattedParts.push(`<pre data-language="${language || 'plaintext'}" class="code-block"><code class="language-${language || 'plaintext'}">${code}</code></pre>`);
        }
    }
    
    // Join parts and clean up
    let result = formattedParts.join('\n');
    
    // Clean up any unwanted tags or spaces
    result = result
        .replace(/<\/pre>\s+<p>/g, '</pre><p>')
        .replace(/<\/p>\s+<pre>/g, '</p><pre>')
        .replace(/\s+$/g, '');
    
    return result;
}

function appendChatMessage(content, type, isHtml = false) {
    const chatHistory = document.getElementById('chatHistory');
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${type} mb-4 p-4 rounded ${type === 'user' ? 'bg-blue-900' : 'bg-gray-800'}`;
    
    if (isHtml) {
        messageDiv.innerHTML = content;
    } else {
        messageDiv.textContent = content;
    }
    
    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return messageDiv;
}

function appendErrorMessage(message) {
    appendChatMessage(`<span class="text-red-500">${message}</span>`, 'assistant', true);
}

// Modal Management
function showApprovalModal(data) {
    const modal = document.getElementById('approvalModal');
    const preview = document.getElementById('changesPreview');
    const modalTitle = modal.querySelector('.modal-header h2');
    const footer = modal.querySelector('.modal-footer .flex');
    
    // Reset modal content
    modalTitle.textContent = data.title || 'Review Changes';
    preview.innerHTML = '';
    footer.innerHTML = '';

    // If it's a file preview
    if (data.isFilePreview) {
        if (data.fileInfo) {
            const fileInfo = document.createElement('div');
            fileInfo.className = 'flex items-center gap-3 mb-6 p-4 bg-gray-700 rounded-lg';
            fileInfo.innerHTML = `
                <i class="${getFileIcon(data.fileInfo.name)} text-xl"></i>
                <div>
                    <h3 class="text-lg font-medium">${data.fileInfo.name}</h3>
                    <p class="text-sm text-gray-400">${data.fileInfo.path}</p>
                </div>
            `;
            preview.appendChild(fileInfo);
        }

        if (data.content) {
            const editorDiv = document.createElement('div');
            editorDiv.style.height = '500px';
            editorDiv.className = 'relative bg-gray-900 rounded-lg';
            
            const textarea = document.createElement('textarea');
            textarea.value = data.content;
            editorDiv.appendChild(textarea);
            preview.appendChild(editorDiv);

            CodeMirror.fromTextArea(textarea, {
                mode: getLanguageMode(data.fileInfo?.path || ''),
                theme: 'monokai',
                lineNumbers: true,
                matchBrackets: true,
                styleActiveLine: true,
                scrollbarStyle: 'overlay',
                readOnly: true
            });

            // Add close button for file preview
            const closeBtn = document.createElement('button');
            closeBtn.className = 'btn btn-secondary';
            closeBtn.textContent = 'Close';
            closeBtn.onclick = hideModal;
            footer.appendChild(closeBtn);
        }
    } else {
        // For code changes preview
        const suggestions = data.suggestions || {};
        
        if (suggestions.explanation) {
            appendExplanation(preview, suggestions.explanation);
        }

        if (suggestions.operations) {
            suggestions.operations.forEach(operation => {
                appendOperation(preview, operation);
            });
            appendModalButtons(footer, suggestions.operations);
        }
    }

    modal.classList.remove('hidden');
}

function appendExplanation(container, explanation) {
    const explanationDiv = document.createElement('div');
    explanationDiv.className = 'mb-6 p-4 bg-gray-700 rounded-lg';
    explanationDiv.innerHTML = `
        <h3 class="text-lg font-medium mb-2">Overview</h3>
        <p class="text-gray-300">${explanation}</p>
    `;
    container.appendChild(explanationDiv);
}

function appendOperation(container, operation) {
    const operationDiv = document.createElement('div');
    operationDiv.className = 'mb-8 bg-gray-700 rounded-lg p-4';

    // Operation header
    const header = document.createElement('div');
    header.className = 'operation-header flex items-center justify-between mb-4';
    
    // Left side: icon and title
    const leftSide = document.createElement('div');
    leftSide.className = 'flex items-center gap-2';
    
    // Icon based on operation type
    const icon = document.createElement('i');
    icon.className = `fas ${getOperationIcon(operation.type)}`;
    leftSide.appendChild(icon);
    
    // Operation title
    const title = document.createElement('span');
    title.className = 'font-medium';
    title.textContent = formatOperationTitle(operation);
    leftSide.appendChild(title);
    
    header.appendChild(leftSide);
    
    // Right side: linter status
    if (operation.lint_passed !== undefined) {
        const linterStatus = document.createElement('div');
        linterStatus.className = 'flex items-center gap-2';
        linterStatus.innerHTML = `
            <i class="fas fa-${operation.lint_passed ? 'check' : 'exclamation-triangle'} text-${operation.lint_passed ? 'green' : 'yellow'}-500"></i>
            <span class="text-sm text-${operation.lint_passed ? 'green' : 'yellow'}-500">
                ${operation.lint_passed ? 'Linter passed' : 'Linter warnings'}
            </span>
        `;
        header.appendChild(linterStatus);
    }
    
    operationDiv.appendChild(header);

    // Operation content
    if (operation.type === 'edit_file' || operation.type === 'create_file') {
        // Show diff if available
        if (operation.diff) {
            const diffDiv = document.createElement('div');
            diffDiv.className = 'bg-gray-900 rounded-lg p-4 font-mono text-sm whitespace-pre overflow-x-auto';
            
            const lines = operation.diff.split('\n');
            const filteredLines = lines.filter((line, index) => line !== '' || index !== lines.length - 1);
            const formattedLines = filteredLines.map(line => {
                if (line.startsWith('---')) {
                    return `<span class="text-red-500">${escapeHtml(line)}</span>`;
                }
                if (line.startsWith('+++')) {
                    return `<span class="text-green-500">${escapeHtml(line)}</span>`;
                }
                if (line.startsWith('+')) {
                    return `<span class="text-green-500">${escapeHtml(line)}</span>`;
                }
                if (line.startsWith('-')) {
                    return `<span class="text-red-500">${escapeHtml(line)}</span>`;
                }
                if (line.startsWith('@@')) {
                    return `<span class="text-blue-500">${escapeHtml(line)}</span>`;
                }
                return `<span class="text-gray-400">${escapeHtml(line)}</span>`;
            });
            
            diffDiv.innerHTML = formattedLines.join('\n');
            operationDiv.appendChild(diffDiv);
        }
        
        // Show lint output if available
        if (operation.lint_output && !operation.lint_passed) {
            const lintDiv = document.createElement('div');
            lintDiv.className = 'mt-4 bg-gray-900 rounded-lg p-4 font-mono text-sm whitespace-pre overflow-x-auto text-yellow-500';
            lintDiv.textContent = operation.lint_output;
            operationDiv.appendChild(lintDiv);
        }
    }
    
    container.appendChild(operationDiv);
}

function getOperationIcon(type) {
    const icons = {
        'create_file': 'fa-solid fa-file-circle-plus text-green-500',
        'edit_file': 'fa-file-edit text-blue-500',
        'remove_file': 'fa-trash text-red-500'
    };
    return icons[type] || 'fa-file text-gray-500';
}

function formatOperationTitle(operation) {
    return `${operation.type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${operation.path}`;
}

function appendModalButtons(footer, operations) {
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.onclick = hideModal;

    const applyBtn = document.createElement('button');
    applyBtn.className = 'btn btn-primary';
    applyBtn.innerHTML = '<i class="fas fa-check mr-2"></i>Apply Changes';
    applyBtn.onclick = () => applyChanges(operations);

    footer.appendChild(cancelBtn);
    footer.appendChild(applyBtn);
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Utility Functions
function showLoading(message = 'Processing...') {
    const loadingOverlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');
    loadingOverlay.classList.remove('hidden');
    loadingText.textContent = message;
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}

function hideModal() {
    document.getElementById('approvalModal').classList.add('hidden');
    
    // Clear status message
    const statusContainer = document.getElementById('statusContainer');
    if (statusContainer) {
        statusContainer.remove();
    }
    
    // Clear progress message
    const progressContainer = document.getElementById('progressContainer');
    if (progressContainer) {
        progressContainer.remove();
    }
}

function showError(message, type = 'error') {
    // Remove any existing notifications
    const existingNotification = document.getElementById('notification');
    if (existingNotification) {
        existingNotification.remove();
    }

    // Create notification element
    const notification = document.createElement('div');
    notification.id = 'notification';
    notification.className = `fixed bottom-4 right-4 p-4 rounded-lg shadow-lg z-50 ${
        type === 'success' ? 'bg-green-500' : 'bg-red-500'
    } text-white`;
    
    notification.innerHTML = `
        <div class="flex items-center gap-2">
            <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
            <span>${message}</span>
        </div>
    `;

    // Add to document
    document.body.appendChild(notification);

    // Remove after 10 seconds (instead of 3)
    setTimeout(() => {
        if (notification && notification.parentNode) {
            notification.remove();
        }
    }, 10000);
}

function validateWorkspace() {
    if (!currentWorkspace) {
        showError('Please create or select a workspace first');
        return false;
    }
    return true;
}

function getLanguageMode(filePath) {
    const ext = filePath.split('.').pop().toLowerCase();
    const modeMap = {
        'js': 'javascript',
        'py': 'python',
        'html': 'xml',
        'css': 'css',
        'json': 'javascript',
        'md': 'markdown',
        'yaml': 'yaml',
        'yml': 'yaml'
    };
    return modeMap[ext] || 'plaintext';
}

async function applyChanges(operations) {
    showLoading('Applying changes...');
    hideModal();

    try {
        const response = await fetch('/apply_changes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workspace_dir: currentWorkspace,
                operations: operations
            })
        });

        const data = await response.json();
        
        if (data.status === 'success') {
            if (data.structure) {
                updateWorkspaceTree(data.structure);
            }
            showError('Changes applied successfully', 'success');
        } else {
            showError(data.message || 'Failed to apply changes');
        }
    } catch (error) {
        console.error('Error:', error);
        showError('Failed to apply changes: ' + error.message);
    } finally {
        hideLoading();
    }
}

// File Viewing
async function showFileContent(filePath) {
    const modal = document.getElementById('approvalModal');
    const preview = document.getElementById('changesPreview');
    const modalTitle = modal.querySelector('.modal-header h2');
    const modalFooter = document.getElementById('modalFooter');

    modalTitle.textContent = filePath.split('/').pop();
    preview.innerHTML = '<div class="text-center p-4"><i class="fas fa-spinner fa-spin mr-2"></i>Loading file...</div>';
    modalFooter.innerHTML = '';
    modal.classList.remove('hidden');

    try {
        // Ensure we're using a clean relative path
        const relativePath = filePath.replace(/^[\/\\]+/, '');
            
        console.log('Current workspace:', currentWorkspace);  // Debug log
        console.log('Original file path:', filePath);  // Debug log
        console.log('Relative path:', relativePath);  // Debug log

        const response = await fetch('/workspace/file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workspace_dir: currentWorkspace,
                file_path: relativePath
            })
        });

        const data = await response.json();
        console.log('File content response:', data);  // Debug log
        
        if (data.status === 'success') {
            // Clear previous content
            preview.innerHTML = '';

            // Create the main container
            const container = document.createElement('div');
            container.className = 'file-preview-container h-full flex flex-col';
            
            // File info header
            const fileInfo = document.createElement('div');
            fileInfo.className = 'file-info-header mb-4 p-4 bg-gray-700 rounded-lg';
            
            // Handle file size display
            const fileSize = formatFileSize(data.file_size);
            console.log('File size:', data.file_size, 'Formatted:', fileSize);  // Debug log
            
            const fileSizeDisplay = data.truncated 
                ? `<p class="text-yellow-400 text-sm mt-1">File is large (${fileSize}). Showing preview of first 1000 lines.</p>` 
                : `<p class="text-gray-400 text-sm mt-1">File size: ${fileSize}</p>`;
            
            fileInfo.innerHTML = `
                <div class="flex items-center gap-3">
                    <i class="fas ${getFileIcon(filePath)}"></i>
                    <div class="flex-1">
                        <div class="flex items-center gap-2">
                            <h3 class="text-lg font-medium">${filePath.split('/').pop()}</h3>
                        </div>
                        <p class="text-sm text-gray-400">${relativePath}</p>
                        ${fileSizeDisplay}
                    </div>
                </div>
            `;
            container.appendChild(fileInfo);

            // File content container
            const contentContainer = document.createElement('div');
            contentContainer.className = 'file-content-container flex-1 bg-gray-800 rounded-lg overflow-hidden';
            contentContainer.style.minHeight = '400px';
            
            // Create editor container
            const editorDiv = document.createElement('div');
            editorDiv.className = 'h-full';
            editorDiv.style.minHeight = '400px';
            
            // Create textarea with content
            const textarea = document.createElement('textarea');
            if (data.content !== undefined && data.content !== null) {
                textarea.value = data.content.replace(/\n$/, '');  // Remove trailing newline if present
                console.log('Content length:', data.content.length);  // Debug log
            } else {
                console.warn('No content received from server');  // Debug log
                textarea.value = '';
            }
            
            editorDiv.appendChild(textarea);
            contentContainer.appendChild(editorDiv);
            container.appendChild(contentContainer);
            
            preview.appendChild(container);

            // Initialize CodeMirror with specific height
            const editor = CodeMirror.fromTextArea(textarea, {
                mode: getLanguageMode(filePath),
                theme: 'monokai',
                lineNumbers: true,
                matchBrackets: true,
                styleActiveLine: true,
                readOnly: true,
                scrollbarStyle: 'overlay',
                lineWrapping: true,
                viewportMargin: Infinity,
                lineSeparator: '\n',
                smartIndent: false,
                electricChars: false,
                extraKeys: null
            });

            // Set editor size and force refresh
            editor.setSize('100%', '400px');
            editor.refresh();  // Immediate refresh
            setTimeout(() => {
                editor.refresh();  // Additional refresh after a short delay
                console.log('Editor refreshed');  // Debug log
            }, 100);

            // Add close button to footer
            const closeBtn = document.createElement('button');
            closeBtn.className = 'btn btn-secondary';
            closeBtn.innerHTML = '<i class="fas fa-times mr-2"></i>Close';
            closeBtn.onclick = hideModal;
            modalFooter.appendChild(closeBtn);
        } else {
            console.error('Error response:', data.message);  // Debug log
            preview.innerHTML = `<div class="text-center text-red-500 p-4">Failed to load file content: ${data.message || 'Unknown error'}</div>`;
        }
    } catch (error) {
        console.error('Error:', error);
        preview.innerHTML = `<div class="text-center text-red-500 p-4">Error loading file: ${error.message}</div>`;
    }
}

function formatFileSize(bytes) {
    if (bytes === undefined || bytes === null || bytes === 0) {
        return 'Empty file';
    }
    
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = Math.abs(bytes);  // Ensure positive number
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }
    
    return `${size.toFixed(1)} ${units[unitIndex]}`;
}

// Keyboard Shortcuts
function initializeKeyboardShortcuts() {
    // Code generation shortcut
    const promptInput = document.getElementById('promptInput');
    promptInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            processPrompt();
        }
    });

    // Chat shortcut
    const chatInput = document.getElementById('chatInput');
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            sendChatMessage();
        }
    });
}

// File attachment handling
async function handleFileAttachment(fileInput, attachmentsContainer) {
    const files = Array.from(fileInput.files);
    attachmentsContainer.innerHTML = '';
    
    for (const file of files) {
        try {
            const content = await extractFileContent(file);
            if (content) {
                addAttachmentToContainer(file.name, content, attachmentsContainer, getFileType(file));
            }
        } catch (error) {
            console.error('Error processing file:', error);
            showError(`Error processing ${file.name}: ${error.message}`);
        }
    }
}

async function extractFileContent(file) {
    const reader = new FileReader();

    // Helper function to wrap FileReader in a promise
    const readFile = (method) => {
        return new Promise((resolve, reject) => {
            reader.onerror = () => reject(new Error('Failed to read file'));
            reader.onload = () => resolve(reader.result);
            method.call(reader, file);
        });
    };

    try {
        switch (true) {
            // PDF Files
            case file.type === 'application/pdf':
                const arrayBuffer = await readFile(reader.readAsArrayBuffer);
                const pdf = await pdfjsLib.getDocument(new Uint8Array(arrayBuffer)).promise;
                let pdfText = '';
                for (let i = 1; i <= pdf.numPages; i++) {
                    const page = await pdf.getPage(i);
                    const textContent = await page.getTextContent();
                    pdfText += textContent.items.map(item => item.str).join(' ') + '\n';
                }
                return pdfText;

            // Word Documents
            case file.type.includes('word') || file.type.includes('openxmlformats-officedocument.wordprocessingml'):
                const docArrayBuffer = await readFile(reader.readAsArrayBuffer);
                const result = await mammoth.extractRawText({ arrayBuffer: docArrayBuffer });
                return result.value;

            // Excel Files
            case file.type.includes('excel') || file.type.includes('spreadsheetml'):
                const excelData = await readFile(reader.readAsArrayBuffer);
                const workbook = XLSX.read(excelData, { type: 'array' });
                let excelText = '';
                workbook.SheetNames.forEach(sheetName => {
                    const sheet = workbook.Sheets[sheetName];
                    excelText += `Sheet: ${sheetName}\n${XLSX.utils.sheet_to_string(sheet)}\n\n`;
                });
                return excelText;

            // Images (OCR)
            case file.type.startsWith('image/'):
                const imageUrl = await readFile(reader.readAsDataURL);
                const worker = await Tesseract.createWorker('eng');
                const { data: { text } } = await worker.recognize(imageUrl);
                await worker.terminate();
                return text;

            // Markdown (Enhanced)
            case file.name.endsWith('.md'):
                const mdContent = await readFile(reader.readAsText);
                const parsed = marked.parse(mdContent, {
                    gfm: true,
                    breaks: true,
                    headerIds: false
                });
                // Strip HTML tags for context
                return parsed.replace(/<[^>]*>/g, ' ');

            // Text and Code Files
            case file.type.startsWith('text/') || 
                 file.type === 'application/json' ||
                 file.name.match(/\.(txt|js|py|java|c|cpp|h|hpp|cs|html|css|json|yml|yaml|xml|sql|sh|bash|r|rb|php|go|rust|swift)$/i):
                return await readFile(reader.readAsText);

            // Default: Try as text
            default:
                if (file.size > 10 * 1024 * 1024) { // 10MB limit for unknown files
                    throw new Error('File too large for unknown type');
                }
                return await readFile(reader.readAsText);
        }
    } catch (error) {
        throw new Error(`Failed to process ${file.name}: ${error.message}`);
    }
}

function getFileType(file) {
    if (file.type === 'application/pdf') return 'pdf';
    if (file.type.includes('word')) return 'word';
    if (file.type.includes('excel')) return 'excel';
    if (file.type.startsWith('image/')) return 'image';
    if (file.name.endsWith('.md')) return 'markdown';
    return 'text';
}

function addAttachmentToContainer(fileName, content, container, type) {
    const fileDiv = document.createElement('div');
    fileDiv.className = 'flex items-center justify-between bg-gray-700 p-2 rounded mb-2';
    fileDiv.dataset.content = content;
    
    const iconMap = {
        'pdf': 'fa-file-pdf text-red-500',
        'word': 'fa-file-word text-blue-500',
        'excel': 'fa-file-excel text-green-500',
        'image': 'fa-file-image text-purple-500',
        'markdown': 'fa-file-alt text-blue-400',
        'text': 'fa-file-code text-blue-500'
    };
    
    const iconClass = iconMap[type] || 'fa-file text-gray-500';
    
    fileDiv.innerHTML = `
        <div class="flex items-center gap-2">
            <i class="fas ${iconClass}"></i>
            <span class="text-sm">${fileName}</span>
            <span class="text-xs text-gray-400">(${formatFileSize(new Blob([content]).size)})</span>
        </div>
        <div class="flex items-center gap-2">
            <button onclick="previewAttachment(this.parentElement.parentElement)" class="text-gray-400 hover:text-blue-500" title="Preview">
                <i class="fas fa-eye"></i>
            </button>
            <button onclick="this.parentElement.parentElement.remove()" class="text-gray-400 hover:text-red-500" title="Remove">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    container.appendChild(fileDiv);
}

function formatFileSize(bytes) {
    if (bytes === undefined || bytes === null || bytes === 0) {
        return 'Empty file';
    }
    
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = Math.abs(bytes);  // Ensure positive number
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
    }
    
    return `${size.toFixed(1)} ${units[unitIndex]}`;
}

function previewAttachment(attachmentDiv) {
    const fileName = attachmentDiv.querySelector('span').textContent;
    const content = attachmentDiv.dataset.content;
    
    const modal = document.getElementById('approvalModal');
    const preview = document.getElementById('changesPreview');
    const modalTitle = modal.querySelector('.modal-header h2');
    const footer = modal.querySelector('.modal-footer .flex');
    
    modalTitle.textContent = `Preview: ${fileName}`;
    preview.innerHTML = '';
    footer.innerHTML = '';
    
    const previewContent = document.createElement('div');
    previewContent.className = 'bg-gray-900 p-4 rounded-lg';
    
    if (fileName.endsWith('.pdf')) {
        // Format PDF content for readability
        const formattedContent = content
            .split('\n')
            .filter(line => line.trim())
            .join('\n\n');
        previewContent.innerHTML = `<pre class="whitespace-pre-wrap font-mono text-sm">${formattedContent}</pre>`;
    } else {
        // For text files, use CodeMirror
        const editorDiv = document.createElement('div');
        editorDiv.style.height = '500px';
        
        const textarea = document.createElement('textarea');
        textarea.value = content;
        previewContent.appendChild(textarea);
        
        CodeMirror.fromTextArea(textarea, {
            mode: getLanguageMode(fileName),
            theme: 'monokai',
            lineNumbers: true,
            readOnly: true,
            viewportMargin: Infinity
        });
    }
    
    preview.appendChild(previewContent);
    
    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn btn-secondary';
    closeBtn.textContent = 'Close';
    closeBtn.onclick = hideModal;
    footer.appendChild(closeBtn);
    
    modal.classList.remove('hidden');
}

// Add event listeners for file inputs
document.getElementById('codeAttachment').addEventListener('change', function() {
    handleFileAttachment(this, document.getElementById('codeAttachments'));
});

document.getElementById('chatAttachment').addEventListener('change', function() {
    handleFileAttachment(this, document.getElementById('chatAttachments'));
});

async function importFolder() {
    await showFolderBrowser();
}

async function showFolderBrowser(path = null) {
    try {
        const modal = document.getElementById('approvalModal');
        const modalTitle = document.getElementById('modalTitle');
        const preview = document.getElementById('changesPreview');
        const footer = document.getElementById('modalFooter');
        
        if (!modal || !modalTitle || !preview || !footer) {
            throw new Error('Modal elements not found');
        }

        showLoading('Loading folders...');
        const response = await fetch(`/available-folders${path ? `?path=${encodeURIComponent(path)}` : ''}`);
        const data = await response.json();
        
        if (data.status !== 'success') {
            throw new Error(data.message || 'Failed to load folders');
        }
        
        modalTitle.textContent = 'Browse Folders';
        preview.innerHTML = `
            <div class="p-4 mb-4 bg-blue-900 bg-opacity-20 rounded-lg">
                <p class="text-sm text-blue-300">
                    <i class="fas fa-info-circle mr-2"></i>
                    Browse to find a folder to import. Click on any folder to navigate into it, or click "Import" when you find the folder you want.
                </p>
            </div>
            <div class="px-4 py-2 bg-gray-800 rounded-lg mb-4 flex items-center gap-2 text-sm">
                <i class="fas fa-folder-open text-blue-400"></i>
                <span class="text-gray-300">${data.current_path}</span>
            </div>
        `;
        footer.innerHTML = '';
        
        // Create folder list
        const folderList = document.createElement('div');
        folderList.className = 'grid grid-cols-1 gap-2';
        
        // Add parent directory navigation if available
        if (data.parent_path) {
            const parentDiv = document.createElement('div');
            parentDiv.className = 'flex items-center p-3 bg-gray-700 rounded-lg hover:bg-gray-600 cursor-pointer transition-colors';
            parentDiv.onclick = () => showFolderBrowser(data.parent_path);
            parentDiv.innerHTML = `
                <div class="flex items-center gap-2">
                    <i class="fas fa-level-up-alt text-gray-400"></i>
                    <span class="font-medium text-gray-300">Parent Directory</span>
                </div>
            `;
            folderList.appendChild(parentDiv);
        }
        
        // Add folders
        data.items.forEach(item => {
            const folderDiv = document.createElement('div');
            folderDiv.className = 'flex items-center justify-between p-3 bg-gray-700 rounded-lg hover:bg-gray-600 cursor-pointer transition-colors';
            
            // Make all folders navigable
            folderDiv.onclick = () => showFolderBrowser(item.path);
            
            const info = document.createElement('div');
            info.className = 'flex-1';
            
            let details = '';
            if (item.is_importable) {
                details = `
                    <div class="text-sm text-gray-400 mt-1">
                        ${item.files} files · ${formatFileSize(item.size)} · 
                        Modified: ${new Date(item.modified * 1000).toLocaleString()}
                    </div>
                `;
            }
            
            info.innerHTML = `
                <div class="flex items-center gap-2">
                    <i class="fas fa-folder${item.is_importable ? '' : '-open'} text-${item.is_importable ? 'blue' : 'gray'}-400"></i>
                    <span class="font-medium text-gray-300">${item.name}</span>
                </div>
                ${details}
            `;
            
            folderDiv.appendChild(info);
            
            // Add import button for importable folders
            if (item.is_importable) {
                const importBtn = document.createElement('button');
                importBtn.className = 'btn btn-primary btn-sm ml-4';
                importBtn.innerHTML = '<i class="fas fa-download mr-1"></i> Import';
                importBtn.onclick = (e) => {
                    e.stopPropagation();  // Prevent folder navigation
                    selectFolderToImport({ ...item, path: item.path });
                };
                folderDiv.appendChild(importBtn);
            } else {
                // Add navigation arrow for all folders
                const arrow = document.createElement('div');
                arrow.innerHTML = '<i class="fas fa-chevron-right text-gray-400"></i>';
                folderDiv.appendChild(arrow);
            }
            
            folderList.appendChild(folderDiv);
        });
        
        preview.appendChild(folderList);
        
        // Add close button
        const closeBtn = document.createElement('button');
        closeBtn.className = 'btn btn-secondary';
        closeBtn.textContent = 'Cancel';
        closeBtn.onclick = hideModal;
        footer.appendChild(closeBtn);
        
        modal.classList.remove('hidden');
    } catch (error) {
        console.error('Error in showFolderBrowser:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

async function selectFolderToImport(folder) {
    try {
        hideModal(); // Hide modal first
        showLoading('Importing folder as workspace...');
        
        const response = await fetch('/workspace/import-folder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                path: folder.path
            })
        });
        
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to import folder');
        }
        
        // Update current workspace
        currentWorkspace = data.workspace_dir;
        
        // Update workspace history and select the workspace
        await loadWorkspaceHistory();
        await selectWorkspace(data.workspace_dir);
        
        showError('Folder imported successfully', 'success');
    } catch (error) {
        console.error('Error importing folder:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

// Add this function to handle recommendations
async function getRecommendations(path, type) {
    if (!validateWorkspace()) return;
    
    const prompt = type === 'directory' ? 
        `Please analyze this folder "${path}" and provide recommendations for best practices, potential improvements, and any issues to look out for.` :
        `Please analyze this file "${path}" and provide recommendations for code improvements, best practices, and potential issues.`;
    
    // Focus the chat tab
    document.getElementById('chatMode').classList.remove('hidden');
    
    // Add user message
    appendChatMessage(prompt, 'user');
    
    // Show loading indicator
    const loadingMessage = appendChatMessage('<i class="fas fa-spinner fa-spin"></i> Analyzing...', 'assistant', true);
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                prompt: prompt,
                workspace_dir: currentWorkspace,
                model_id: document.getElementById('modelSelect').value,
                context_path: path
            })
        });

        const data = await response.json();
        
        // Remove loading message
        loadingMessage.remove();

        if (data.status === 'success') {
            const formattedResponse = formatChatResponse(data.response);
            appendChatMessage(formattedResponse, 'assistant', true);
        } else {
            appendErrorMessage(data.message || 'Failed to get recommendations');
        }
    } catch (error) {
        console.error('Error:', error);
        loadingMessage.remove();
        appendErrorMessage('Error: ' + error.message);
    }
}

async function getCodeGeneration(path, type) {
    if (!validateWorkspace()) return;
    
    const prompt = type === 'directory' ? 
        `Please help me modify or generate code for the folder "${path}". Suggest improvements, new files, or modifications.` :
        `Please help me modify or generate code for the file "${path}". Suggest improvements or modifications.`;
    
    // Set the prompt in the input field
    const promptInput = document.getElementById('promptInput');
    promptInput.value = prompt;
    
    // Trigger the code generation
    await processPrompt();
} 