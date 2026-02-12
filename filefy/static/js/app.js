/**
 * Filer - Professional File Manager JavaScript
 * Handles all client-side interactions
 */

// Application State
const state = {
    currentPath: null,
    selectedItem: null,
    clipboard: null,
    clipboardAction: null, // 'copy' or 'cut'
    viewMode: 'grid',
    downloadTasks: {},
    uploadFiles: [],
    browserPath: null
};

// DOM Elements
const elements = {
    fileList: document.getElementById('fileList'),
    fileContainer: document.getElementById('fileContainer'),
    breadcrumb: document.getElementById('breadcrumb'),
    searchInput: document.getElementById('searchInput'),
    statusText: document.getElementById('statusText'),
    itemCount: document.getElementById('itemCount'),
    contextMenu: document.getElementById('contextMenu'),
    detailsPanel: document.getElementById('detailsPanel'),
    detailsContent: document.getElementById('detailsContent'),
    downloadList: document.getElementById('downloadList'),
    diskProgressBar: document.getElementById('diskProgressBar'),
    diskUsed: document.getElementById('diskUsed'),
    diskTotal: document.getElementById('diskTotal'),
    loadingOverlay: document.getElementById('loadingOverlay'),
    toastContainer: document.getElementById('toastContainer')
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    init();
});

function init() {
    // Load initial directory
    browseDirectory('~');
    
    // Load disk usage
    loadDiskUsage();
    
    // Start download progress monitoring
    setInterval(updateDownloadProgress, 1000);
    
    // Setup event listeners
    setupEventListeners();
}

// Event Listeners Setup
function setupEventListeners() {
    // Quick links in sidebar
    document.querySelectorAll('.quick-links li').forEach(item => {
        item.addEventListener('click', () => {
            browseDirectory(item.dataset.path);
        });
    });

    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', () => {
        browseDirectory(state.currentPath);
        showToast('Refreshed', 'info');
    });

    // View toggle buttons
    document.getElementById('gridViewBtn').addEventListener('click', () => {
        setViewMode('grid');
    });

    document.getElementById('listViewBtn').addEventListener('click', () => {
        setViewMode('list');
    });

    // Upload button
    document.getElementById('uploadBtn').addEventListener('click', () => {
        openModal('uploadModal');
        document.getElementById('uploadFileList').innerHTML = '';
        state.uploadFiles = [];
        document.getElementById('startUploadBtn').disabled = true;
    });

    // New folder button
    document.getElementById('newFolderBtn').addEventListener('click', () => {
        openModal('newFolderModal');
        document.getElementById('folderName').value = '';
        document.getElementById('folderName').focus();
    });

    // Remote download button
    document.getElementById('newRemoteDownload').addEventListener('click', () => {
        openModal('remoteDownloadModal');
        document.getElementById('downloadUrl').value = '';
        document.getElementById('downloadDestination').textContent = state.currentPath;
    });

    // Upload zone interactions
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');

    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        handleFileSelection(e.dataTransfer.files);
    });

    document.getElementById('selectFilesBtn').addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        handleFileSelection(e.target.files);
    });

    // Start upload button
    document.getElementById('startUploadBtn').addEventListener('click', () => {
        uploadFiles();
    });

    // Create folder button
    document.getElementById('createFolderBtn').addEventListener('click', () => {
        createFolder();
    });

    // Folder name input - enter key
    document.getElementById('folderName').addEventListener('keyup', (e) => {
        if (e.key === 'Enter') createFolder();
    });

    // Start remote download button
    document.getElementById('startRemoteDownloadBtn').addEventListener('click', () => {
        startRemoteDownload();
    });

    // Rename confirm button
    document.getElementById('confirmRenameBtn').addEventListener('click', () => {
        renameItem();
    });

    // New name input - enter key
    document.getElementById('newName').addEventListener('keyup', (e) => {
        if (e.key === 'Enter') renameItem();
    });

    // Delete confirm button
    document.getElementById('confirmDeleteBtn').addEventListener('click', () => {
        deleteItem();
    });

    // Move/Copy confirm button
    document.getElementById('confirmMoveBtn').addEventListener('click', () => {
        confirmMoveCopy();
    });

    // Close details panel
    document.getElementById('closeDetailsBtn').addEventListener('click', () => {
        elements.detailsPanel.classList.remove('open');
        state.selectedItem = null;
        clearSelection();
    });

    // Close modals on background click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal(modal.id);
            }
        });
    });

    // Close modal buttons
    document.querySelectorAll('.close-modal').forEach(btn => {
        btn.addEventListener('click', () => {
            const modal = btn.closest('.modal');
            closeModal(modal.id);
        });
    });

    // Context menu items
    document.querySelectorAll('.context-menu li[data-action]').forEach(item => {
        item.addEventListener('click', () => {
            handleContextAction(item.dataset.action);
            hideContextMenu();
        });
    });

    // Hide context menu on click outside
    document.addEventListener('click', (e) => {
        if (!elements.contextMenu.contains(e.target)) {
            hideContextMenu();
        }
    });

    // File container click (deselect)
    elements.fileContainer.addEventListener('click', (e) => {
        if (e.target === elements.fileContainer || e.target === elements.fileList) {
            clearSelection();
            elements.detailsPanel.classList.remove('open');
        }
    });

    // Search input
    let searchTimeout;
    elements.searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            if (e.target.value.trim()) {
                searchFiles(e.target.value.trim());
            } else {
                browseDirectory(state.currentPath);
            }
        }, 300);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        if (e.key === 'Delete' && state.selectedItem) {
            showDeleteConfirm();
        } else if (e.key === 'F2' && state.selectedItem) {
            e.preventDefault();
            showRenameDialog();
        } else if (e.key === 'F5') {
            e.preventDefault();
            browseDirectory(state.currentPath);
            showToast('Refreshed', 'info');
        } else if (e.ctrlKey && e.key === 'c' && state.selectedItem) {
            e.preventDefault();
            copyItem();
        } else if (e.ctrlKey && e.key === 'x' && state.selectedItem) {
            e.preventDefault();
            cutItem();
        } else if (e.ctrlKey && e.key === 'v' && state.clipboard) {
            e.preventDefault();
            showPasteDialog();
        } else if (e.key === 'Escape') {
            hideContextMenu();
            closeAllModals();
        }
    });
}

// Browse Directory
async function browseDirectory(path) {
    showLoading();
    try {
        const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();
        
        if (response.ok) {
            state.currentPath = data.current_path;
            renderBreadcrumb(data.current_path);
            renderFileList(data.items);
            elements.itemCount.textContent = `${data.total_items} items`;
            elements.statusText.textContent = 'Ready';
        } else {
            showToast(data.error || 'Failed to browse directory', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Render Breadcrumb
function renderBreadcrumb(path) {
    const parts = path.split('/').filter(p => p);
    let currentPath = '';
    
    let html = `<span class="breadcrumb-item" data-path="/">
        <i class="fas fa-hdd"></i>
    </span>`;
    
    parts.forEach((part, index) => {
        currentPath += '/' + part;
        const isLast = index === parts.length - 1;
        html += `<span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-item ${isLast ? 'active' : ''}" data-path="${currentPath}">${part}</span>`;
    });
    
    elements.breadcrumb.innerHTML = html;
    
    // Add click handlers
    elements.breadcrumb.querySelectorAll('.breadcrumb-item').forEach(item => {
        item.addEventListener('click', () => {
            browseDirectory(item.dataset.path);
        });
    });
}

// Render File List
function renderFileList(items) {
    if (items.length === 0) {
        elements.fileList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-folder-open"></i>
                <p>This folder is empty</p>
            </div>
        `;
        return;
    }
    
    let html = '';
    
    if (state.viewMode === 'grid') {
        items.forEach(item => {
            html += `
                <div class="file-item" data-path="${item.path}" data-is-dir="${item.is_dir}">
                    <i class="fas ${item.icon} file-icon"></i>
                    <span class="file-name">${escapeHtml(item.name)}</span>
                </div>
            `;
        });
    } else {
        items.forEach(item => {
            html += `
                <div class="file-item" data-path="${item.path}" data-is-dir="${item.is_dir}">
                    <i class="fas ${item.icon} file-icon"></i>
                    <span class="file-name">${escapeHtml(item.name)}</span>
                    <span class="file-size">${item.size_formatted}</span>
                    <span class="file-modified">${item.modified}</span>
                    <span class="file-perms">${item.permissions}</span>
                </div>
            `;
        });
    }
    
    elements.fileList.innerHTML = html;
    
    // Add event listeners to file items
    elements.fileList.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            selectItem(item);
        });
        
        item.addEventListener('dblclick', () => {
            openItem(item);
        });
        
        item.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            selectItem(item);
            showContextMenu(e.pageX, e.pageY);
        });
    });
}

// Select Item
function selectItem(item) {
    clearSelection();
    item.classList.add('selected');
    state.selectedItem = {
        path: item.dataset.path,
        isDir: item.dataset.isDir === 'true'
    };
    
    // Show details panel
    showItemDetails(item.dataset.path);
}

// Clear Selection
function clearSelection() {
    elements.fileList.querySelectorAll('.file-item.selected').forEach(item => {
        item.classList.remove('selected');
    });
    state.selectedItem = null;
}

// Open Item
function openItem(item) {
    const path = item.dataset.path;
    const isDir = item.dataset.isDir === 'true';
    
    if (isDir) {
        browseDirectory(path);
    } else {
        // Preview file or download based on type
        previewFile(path);
    }
}

// Show Item Details
async function showItemDetails(path) {
    try {
        const response = await fetch(`/api/file-info?path=${encodeURIComponent(path)}`);
        const data = await response.json();
        
        if (response.ok) {
            const isImage = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'].includes(data.extension.toLowerCase());
            
            let previewHtml = '';
            if (isImage) {
                previewHtml = `<img src="/api/preview/${encodeURIComponent(path)}" alt="${escapeHtml(data.name)}">`;
            } else {
                previewHtml = `<i class="fas ${data.icon} file-icon"></i>`;
            }
            
            elements.detailsContent.innerHTML = `
                <div class="detail-preview">${previewHtml}</div>
                <div class="detail-info">
                    <div class="detail-name">${escapeHtml(data.name)}</div>
                    <div class="detail-row">
                        <span class="label">Type</span>
                        <span class="value">${data.is_dir ? 'Folder' : (data.extension || 'File')}</span>
                    </div>
                    <div class="detail-row">
                        <span class="label">Size</span>
                        <span class="value">${data.size_formatted}</span>
                    </div>
                    <div class="detail-row">
                        <span class="label">Modified</span>
                        <span class="value">${data.modified}</span>
                    </div>
                    <div class="detail-row">
                        <span class="label">Permissions</span>
                        <span class="value">${data.permissions}</span>
                    </div>
                </div>
                <div class="detail-actions">
                    <button class="btn btn-primary btn-full" onclick="downloadSelectedItem()">
                        <i class="fas fa-download"></i> Download
                    </button>
                    <button class="btn btn-secondary btn-full" onclick="showRenameDialog()">
                        <i class="fas fa-edit"></i> Rename
                    </button>
                    <button class="btn btn-danger btn-full" onclick="showDeleteConfirm()">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            `;
            
            elements.detailsPanel.classList.add('open');
        }
    } catch (error) {
        console.error('Failed to load item details:', error);
    }
}

// Set View Mode
function setViewMode(mode) {
    state.viewMode = mode;
    
    document.getElementById('gridViewBtn').classList.toggle('active', mode === 'grid');
    document.getElementById('listViewBtn').classList.toggle('active', mode === 'list');
    
    elements.fileList.classList.remove('grid-view', 'list-view');
    elements.fileList.classList.add(`${mode}-view`);
    
    // Re-render current directory
    browseDirectory(state.currentPath);
}

// Context Menu
function showContextMenu(x, y) {
    // Update paste button state based on clipboard
    const pasteBtn = document.getElementById('ctxPaste');
    if (pasteBtn) {
        if (state.clipboard) {
            pasteBtn.classList.remove('disabled');
        } else {
            pasteBtn.classList.add('disabled');
        }
    }
    
    elements.contextMenu.style.left = `${x}px`;
    elements.contextMenu.style.top = `${y}px`;
    elements.contextMenu.classList.add('show');
    
    // Adjust position if menu goes off screen
    const rect = elements.contextMenu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
        elements.contextMenu.style.left = `${x - rect.width}px`;
    }
    if (rect.bottom > window.innerHeight) {
        elements.contextMenu.style.top = `${y - rect.height}px`;
    }
}

function hideContextMenu() {
    elements.contextMenu.classList.remove('show');
}

function handleContextAction(action) {
    switch (action) {
        case 'open':
            if (!state.selectedItem) return;
            const item = document.querySelector(`.file-item[data-path="${state.selectedItem.path}"]`);
            if (item) openItem(item);
            break;
        case 'preview':
            if (!state.selectedItem) return;
            if (!state.selectedItem.is_dir) {
                previewFile(state.selectedItem.path);
            } else {
                showToast('Cannot preview folders', 'warning');
            }
            break;
        case 'download':
            if (!state.selectedItem) return;
            downloadSelectedItem();
            break;
        case 'copy':
            if (!state.selectedItem) return;
            copyItem();
            break;
        case 'cut':
            if (!state.selectedItem) return;
            cutItem();
            break;
        case 'paste':
            showPasteDialog();
            break;
        case 'duplicate':
            if (!state.selectedItem) return;
            duplicateItem();
            break;
        case 'rename':
            if (!state.selectedItem) return;
            showRenameDialog();
            break;
        case 'move':
            if (!state.selectedItem) return;
            state.clipboard = state.selectedItem.path;
            state.clipboardAction = 'cut';
            showPasteDialog();
            break;
        case 'copyto':
            if (!state.selectedItem) return;
            state.clipboard = state.selectedItem.path;
            state.clipboardAction = 'copy';
            showPasteDialog();
            break;
        case 'newfolder':
            openModal('newFolderModal');
            document.getElementById('folderName').value = '';
            document.getElementById('folderName').focus();
            break;
        case 'refresh':
            browseDirectory(state.currentPath);
            showToast('Refreshed', 'info');
            break;
        case 'delete':
            if (!state.selectedItem) return;
            showDeleteConfirm();
            break;
        case 'info':
            if (!state.selectedItem) return;
            showPropertiesDialog();
            break;
    }
}

// Duplicate Item
async function duplicateItem() {
    if (!state.selectedItem) return;
    
    showLoading();
    try {
        const response = await fetch('/api/copy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source: state.selectedItem.path,
                destination: state.currentPath
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('Item duplicated', 'success');
            browseDirectory(state.currentPath);
        } else {
            showToast(data.error || 'Failed to duplicate', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Copy/Cut/Paste
function copyItem() {
    if (!state.selectedItem) return;
    state.clipboard = state.selectedItem.path;
    state.clipboardAction = 'copy';
    showToast('Item copied to clipboard', 'info');
}

function cutItem() {
    if (!state.selectedItem) return;
    state.clipboard = state.selectedItem.path;
    state.clipboardAction = 'cut';
    showToast('Item cut to clipboard', 'info');
}

function showPasteDialog() {
    if (!state.clipboard) {
        showToast('Clipboard is empty', 'warning');
        return;
    }
    
    state.browserPath = state.currentPath;
    document.getElementById('browserPath').textContent = state.browserPath;
    document.getElementById('moveCopyTitle').innerHTML = state.clipboardAction === 'copy' 
        ? '<i class="fas fa-copy"></i> Copy to...'
        : '<i class="fas fa-scissors"></i> Move to...';
    document.getElementById('confirmMoveBtn').textContent = state.clipboardAction === 'copy' ? 'Copy Here' : 'Move Here';
    
    loadFolderBrowser(state.browserPath);
    openModal('moveCopyModal');
}

async function loadFolderBrowser(path) {
    try {
        const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();
        
        if (response.ok) {
            state.browserPath = data.current_path;
            document.getElementById('browserPath').textContent = state.browserPath;
            
            let html = '';
            
            // Parent directory
            if (data.parent_path) {
                html += `<div class="folder-item parent" data-path="${data.parent_path}">
                    <i class="fas fa-level-up-alt"></i>
                    <span>..</span>
                </div>`;
            }
            
            // Folders only
            data.items.filter(item => item.is_dir).forEach(item => {
                html += `<div class="folder-item" data-path="${item.path}">
                    <i class="fas fa-folder"></i>
                    <span>${escapeHtml(item.name)}</span>
                </div>`;
            });
            
            document.getElementById('folderList').innerHTML = html;
            
            // Add click handlers
            document.querySelectorAll('#folderList .folder-item').forEach(item => {
                item.addEventListener('click', () => {
                    loadFolderBrowser(item.dataset.path);
                });
            });
        }
    } catch (error) {
        showToast('Failed to load folders', 'error');
    }
}

async function confirmMoveCopy() {
    if (!state.clipboard || !state.browserPath) return;
    
    const endpoint = state.clipboardAction === 'copy' ? '/api/copy' : '/api/move';
    
    showLoading();
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source: state.clipboard,
                destination: state.browserPath
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast(data.message, 'success');
            state.clipboard = null;
            state.clipboardAction = null;
            closeModal('moveCopyModal');
            browseDirectory(state.currentPath);
        } else {
            showToast(data.error || 'Operation failed', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Download
function downloadSelectedItem() {
    if (!state.selectedItem) return;
    
    const link = document.createElement('a');
    link.href = `/api/download/${encodeURIComponent(state.selectedItem.path)}`;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// File Upload
function handleFileSelection(files) {
    state.uploadFiles = Array.from(files);
    
    let html = '';
    state.uploadFiles.forEach((file, index) => {
        html += `
            <div class="upload-file-item">
                <i class="fas fa-file"></i>
                <div class="file-info">
                    <div class="file-name">${escapeHtml(file.name)}</div>
                    <div class="file-size">${formatSize(file.size)}</div>
                </div>
                <i class="fas fa-times remove-file" data-index="${index}"></i>
            </div>
        `;
    });
    
    document.getElementById('uploadFileList').innerHTML = html;
    document.getElementById('startUploadBtn').disabled = state.uploadFiles.length === 0;
    
    // Remove file handlers
    document.querySelectorAll('.remove-file').forEach(btn => {
        btn.addEventListener('click', () => {
            state.uploadFiles.splice(parseInt(btn.dataset.index), 1);
            handleFileSelection(state.uploadFiles);
        });
    });
}

async function uploadFiles() {
    if (state.uploadFiles.length === 0) return;
    
    const formData = new FormData();
    formData.append('path', state.currentPath);
    state.uploadFiles.forEach(file => {
        formData.append('files', file);
    });
    
    showLoading();
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast(data.message, 'success');
            closeModal('uploadModal');
            browseDirectory(state.currentPath);
        } else {
            showToast(data.error || 'Upload failed', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Create Folder
async function createFolder() {
    const name = document.getElementById('folderName').value.trim();
    if (!name) {
        showToast('Please enter a folder name', 'warning');
        return;
    }
    
    showLoading();
    try {
        const response = await fetch('/api/create-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: state.currentPath,
                name: name
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('Folder created successfully', 'success');
            closeModal('newFolderModal');
            browseDirectory(state.currentPath);
        } else {
            showToast(data.error || 'Failed to create folder', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Rename
function showRenameDialog() {
    if (!state.selectedItem) return;
    
    const name = state.selectedItem.path.split('/').pop();
    document.getElementById('newName').value = name;
    openModal('renameModal');
    document.getElementById('newName').focus();
    document.getElementById('newName').select();
}

async function renameItem() {
    if (!state.selectedItem) return;
    
    const newName = document.getElementById('newName').value.trim();
    if (!newName) {
        showToast('Please enter a new name', 'warning');
        return;
    }
    
    showLoading();
    try {
        const response = await fetch('/api/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: state.selectedItem.path,
                new_name: newName
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('Renamed successfully', 'success');
            closeModal('renameModal');
            browseDirectory(state.currentPath);
        } else {
            showToast(data.error || 'Failed to rename', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Delete
function showDeleteConfirm() {
    if (!state.selectedItem) return;
    
    const name = state.selectedItem.path.split('/').pop();
    document.getElementById('deleteItemName').textContent = name;
    openModal('deleteModal');
}

async function deleteItem() {
    if (!state.selectedItem) return;
    
    showLoading();
    try {
        const response = await fetch('/api/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: state.selectedItem.path
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showToast('Deleted successfully', 'success');
            closeModal('deleteModal');
            elements.detailsPanel.classList.remove('open');
            state.selectedItem = null;
            browseDirectory(state.currentPath);
        } else {
            showToast(data.error || 'Failed to delete', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Properties Dialog
async function showPropertiesDialog() {
    if (!state.selectedItem) return;
    
    try {
        const response = await fetch(`/api/file-info?path=${encodeURIComponent(state.selectedItem.path)}`);
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('propertiesContent').innerHTML = `
                <div class="properties-icon">
                    <i class="fas ${data.icon} file-icon"></i>
                </div>
                <table class="properties-table">
                    <tr><td>Name</td><td>${escapeHtml(data.name)}</td></tr>
                    <tr><td>Type</td><td>${data.is_dir ? 'Folder' : (data.extension || 'File')}</td></tr>
                    <tr><td>Location</td><td>${escapeHtml(data.path)}</td></tr>
                    <tr><td>Size</td><td>${data.size_formatted}</td></tr>
                    <tr><td>Created</td><td>${data.created}</td></tr>
                    <tr><td>Modified</td><td>${data.modified}</td></tr>
                    <tr><td>Permissions</td><td>${data.permissions}</td></tr>
                </table>
            `;
            openModal('propertiesModal');
        }
    } catch (error) {
        showToast('Failed to load properties', 'error');
    }
}

// Preview File
async function previewFile(path) {
    showLoading();
    try {
        const response = await fetch(`/api/preview/${encodeURIComponent(path)}`);
        
        if (response.ok) {
            const contentType = response.headers.get('content-type');
            const filename = path.split('/').pop();
            document.getElementById('previewFileName').textContent = filename;
            
            if (contentType && contentType.startsWith('image/')) {
                document.getElementById('previewContent').innerHTML = `
                    <img src="/api/preview/${encodeURIComponent(path)}" alt="${escapeHtml(filename)}">
                `;
            } else {
                const data = await response.json();
                if (data.type === 'text') {
                    document.getElementById('previewContent').innerHTML = `
                        <pre>${escapeHtml(data.content)}</pre>
                    `;
                } else {
                    showToast(data.error || 'Cannot preview this file type', 'warning');
                    hideLoading();
                    return;
                }
            }
            openModal('previewModal');
        } else {
            const data = await response.json();
            showToast(data.error || 'Cannot preview file', 'warning');
        }
    } catch (error) {
        showToast('Failed to preview file', 'error');
    }
    hideLoading();
}

// Remote Download
async function startRemoteDownload() {
    const url = document.getElementById('downloadUrl').value.trim();
    if (!url) {
        showToast('Please enter a URL', 'warning');
        return;
    }

    // Validate URL format
    try {
        new URL(url);
    } catch (e) {
        showToast('Invalid URL format', 'error');
        return;
    }

    const destination = state.currentPath || '~';
    console.log('Starting remote download:', { url, destination });
    
    showLoading();
    try {
        const response = await fetch('/api/remote-download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                destination: destination
            })
        });
        
        const data = await response.json();
        console.log('Remote download response:', data);
        
        if (response.ok) {
            showToast('Download started: ' + (data.task_id || 'Unknown ID'), 'success');
            state.downloadTasks[data.task_id] = true;
            document.getElementById('downloadUrl').value = '';
            closeModal('remoteDownloadModal');
            // Immediately update download progress
            setTimeout(updateDownloadProgress, 500);
        } else {
            showToast(data.error || 'Failed to start download', 'error');
        }
    } catch (error) {
        console.error('Remote download error:', error);
        showToast('Network error: ' + error.message, 'error');
    }
    hideLoading();
}

async function updateDownloadProgress() {
    try {
        const response = await fetch('/api/download-tasks');
        if (!response.ok) {
            console.error('Failed to fetch download tasks:', response.status);
            return;
        }
        const tasks = await response.json();
        
        if (!Array.isArray(tasks)) {
            console.error('Download tasks response is not an array:', tasks);
            return;
        }
        
        let html = '';
        tasks.forEach(task => {
            const statusClass = task.status || 'pending';
            const progress = task.progress || 0;
            const filename = task.filename || 'Downloading...';
            const url = task.url || '';
            
            html += `
                <div class="download-item ${statusClass}" data-id="${task.id}">
                    <div class="download-item-header">
                        <span class="download-filename" title="${escapeHtml(url)}">
                            ${escapeHtml(filename)}
                        </span>
                        <span class="download-status ${statusClass}">${statusClass}</span>
                    </div>
                    <div class="download-progress">
                        <div class="download-progress-bar" style="width: ${progress}%"></div>
                    </div>
                    <div class="download-info">
                        <span>${task.downloaded_formatted || '0 B'} / ${task.total_size_formatted || 'Unknown'}</span>
                        <span>${task.speed_formatted || '0 B/s'}</span>
                    </div>
                    ${statusClass === 'downloading' || statusClass === 'pending' ? `
                        <div class="download-actions">
                            <button class="btn btn-sm btn-danger" onclick="cancelDownload('${task.id}')">
                                <i class="fas fa-stop"></i> Cancel
                            </button>
                        </div>
                    ` : ''}
                    ${statusClass === 'error' ? `
                        <div class="download-error">
                            <i class="fas fa-exclamation-circle"></i> ${escapeHtml(task.error || 'Download failed')}
                        </div>
                    ` : ''}
                    ${statusClass === 'completed' ? `
                        <div class="download-complete">
                            <i class="fas fa-check-circle"></i> Complete
                        </div>
                    ` : ''}
                </div>
            `;
        });
        
        if (html) {
            elements.downloadList.innerHTML = html;
        } else {
            elements.downloadList.innerHTML = '<p style="color: var(--text-muted); font-size: 13px; text-align: center; padding: 20px;">No active downloads</p>';
        }
    } catch (error) {
        console.error('Failed to update download progress:', error);
    }
}

async function cancelDownload(taskId) {
    try {
        await fetch(`/api/cancel-download/${taskId}`, { method: 'POST' });
        showToast('Download cancelled', 'info');
    } catch (error) {
        showToast('Failed to cancel download', 'error');
    }
}

// Search Files
async function searchFiles(query) {
    showLoading();
    try {
        const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&path=${encodeURIComponent(state.currentPath)}`);
        const data = await response.json();
        
        if (response.ok) {
            renderFileList(data.results);
            elements.itemCount.textContent = `${data.total} results`;
            elements.statusText.textContent = `Search: "${query}"`;
        } else {
            showToast(data.error || 'Search failed', 'error');
        }
    } catch (error) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// Disk Usage
async function loadDiskUsage() {
    try {
        const response = await fetch('/api/disk-usage');
        const data = await response.json();
        
        if (response.ok) {
            elements.diskProgressBar.style.width = `${data.percent_used}%`;
            elements.diskUsed.textContent = data.used_formatted;
            elements.diskTotal.textContent = data.total_formatted;
        }
    } catch (error) {
        console.error('Failed to load disk usage:', error);
    }
}

// Modal Helpers
function openModal(modalId) {
    document.getElementById(modalId).classList.add('show');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('show');
}

function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('show');
    });
}

// Loading Helpers
function showLoading() {
    elements.loadingOverlay.classList.add('show');
}

function hideLoading() {
    elements.loadingOverlay.classList.remove('show');
}

// Toast Notifications
function showToast(message, type = 'info') {
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="fas ${icons[type]}"></i>
        <span class="toast-message">${escapeHtml(message)}</span>
        <span class="toast-close"><i class="fas fa-times"></i></span>
    `;
    
    elements.toastContainer.appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
    
    // Manual remove on click
    toast.querySelector('.toast-close').addEventListener('click', () => {
        toast.remove();
    });
}

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatSize(bytes) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return `${bytes.toFixed(2)} ${units[i]}`;
}
