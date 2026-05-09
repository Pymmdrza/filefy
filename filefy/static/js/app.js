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
    uploadFiles: [],
    browserPath: null,
    // Local registry of all in-flight transfers (uploads, local
    // downloads, and remote downloads). Keyed by a synthetic id; each
    // entry holds the data needed to render and control the transfer.
    transfers: {},
    transferPanelHidden: true,
    transferPanelMinimized: false,
    // Peer tab support
    activeTabPeer: null,    // null = local tab; string peerId = remote tab
    remoteTabs: {},         // peerId -> { currentPath: string, selectedItem }
};

// DOM Elements
const elements = {
    fileList: document.getElementById('fileList'),
    fileContainer: document.getElementById('fileContainer'),
    breadcrumb: document.getElementById('breadcrumb'),
    searchInput: document.getElementById('searchInput'),
    statusText: document.getElementById('statusText'),
    itemCount: document.getElementById('itemCount'),
    peerBadge: document.getElementById('peerBadge'),
    peerBadgeText: document.getElementById('peerBadgeText'),
    contextMenu: document.getElementById('contextMenu'),
    detailsPanel: document.getElementById('detailsPanel'),
    detailsContent: document.getElementById('detailsContent'),
    diskProgressBar: document.getElementById('diskProgressBar'),
    diskUsed: document.getElementById('diskUsed'),
    diskTotal: document.getElementById('diskTotal'),
    opState: document.getElementById('opState'),
    opQueue: document.getElementById('opQueue'),
    opStorage: document.getElementById('opStorage'),
    opPath: document.getElementById('opPath'),
    opClock: document.getElementById('opClock'),
    loadingOverlay: document.getElementById('loadingOverlay'),
    toastContainer: document.getElementById('toastContainer'),
    quickLinks: document.getElementById('quickLinks'),
    // Transfer center
    transferCenter: document.getElementById('transferCenter'),
    transferList: document.getElementById('transferList'),
    transferEmpty: document.getElementById('transferEmpty'),
    transferCountBadge: document.getElementById('transferCountBadge'),
    transferReopenBtn: document.getElementById('transferReopenBtn'),
    transferReopenLabel: document.getElementById('transferReopenLabel'),
    sidebarTransfers: document.getElementById('sidebarTransfers'),
    // Tunnel info
    tunnelSection: document.getElementById('tunnelSection'),
    tunnelStatus: document.getElementById('tunnelStatus'),
    tunnelUrl: document.getElementById('tunnelUrl')
};

// Server-reported home/base directory (set after /api/quick-access loads)
let serverHome = null;

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    init();
});

function init() {
    // Load Quick Access shortcuts dynamically from the host system,
    // then start browsing the server-reported base directory. This makes
    // the sidebar reflect the *actual* machine (or Docker mount) rather
    // than relying on hardcoded paths.
    loadQuickAccess();

    // Load disk usage and tunnel/server info
    loadDiskUsage();
    loadServerInfo();

    // Periodically poll remote-download progress and refresh the
    // unified Transfer Center / sidebar views.
    setInterval(refreshRemoteDownloads, 1000);
    setInterval(updateOperationsClock, 1000);
    setInterval(loadServerInfo, 15000);
    updateOperationsClock();
    renderTransfers();

    // Setup event listeners
    setupEventListeners();
    setupTransferCenter();
}

// Load Quick Access shortcuts from the server and render them in the sidebar
async function loadQuickAccess() {
    try {
        const response = await fetch('/api/quick-access');
        const data = await response.json();

        if (response.ok) {
            serverHome = data.home || null;
            renderQuickAccess(data.items || []);
        } else {
            console.error('Failed to load quick access:', data);
        }
    } catch (error) {
        console.error('Quick access network error:', error);
    } finally {
        // Whether or not the sidebar loaded, always navigate to a sensible
        // starting directory (the server's base dir, or "~" as a fallback).
        browseDirectory(serverHome || '~');
    }
}

function renderQuickAccess(items) {
    if (!elements.quickLinks) return;

    if (!items.length) {
        elements.quickLinks.innerHTML =
            '<li class="quick-empty" style="cursor:default;opacity:0.6;">No locations available</li>';
        return;
    }

    elements.quickLinks.innerHTML = items.map(item => `
        <li data-path="${escapeHtml(item.path)}" title="${escapeHtml(item.path)}">
            <i class="fas ${sanitizeIconClass(item.icon)}"></i>
            ${escapeHtml(item.label)}
        </li>
    `).join('');
}

// Restrict icon strings to a safe FontAwesome-style class token so they can
// be inserted into the class attribute without HTML-escaping (which would
// break the CSS selector) while still rejecting anything unexpected.
function sanitizeIconClass(icon) {
    if (typeof icon !== 'string') return 'fa-folder';
    return /^fa-[a-z0-9]+(-[a-z0-9]+)*$/i.test(icon) ? icon : 'fa-folder';
}

// Event Listeners Setup
function setupEventListeners() {
    // Quick links in sidebar (event delegation since items are loaded dynamically)
    if (elements.quickLinks) {
        elements.quickLinks.addEventListener('click', (e) => {
            const li = e.target.closest('li[data-path]');
            if (li) {
                browseDirectory(li.dataset.path);
            }
        });
    }

    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', () => {
        if (state.activeTabPeer) {
            const tab = state.remoteTabs[state.activeTabPeer];
            browseRemoteDirectory(state.activeTabPeer, tab ? tab.currentPath : '');
        } else {
            browseDirectory(state.currentPath);
        }
        showToast('Refreshed', 'info');
    });

    // View toggle buttons (local)
    document.getElementById('gridViewBtn').addEventListener('click', () => {
        setViewMode('grid');
    });

    document.getElementById('listViewBtn').addEventListener('click', () => {
        setViewMode('list');
    });

    // View toggle buttons (remote)
    document.getElementById('remoteGridViewBtn').addEventListener('click', () => {
        setViewMode('grid');
    });

    document.getElementById('remoteListViewBtn').addEventListener('click', () => {
        setViewMode('list');
    });

    // Upload button (local)
    document.getElementById('uploadBtn').addEventListener('click', () => {
        openModal('uploadModal');
        document.getElementById('uploadFileList').innerHTML = '';
        state.uploadFiles = [];
        document.getElementById('startUploadBtn').disabled = true;
    });

    // New folder button (local)
    document.getElementById('newFolderBtn').addEventListener('click', () => {
        openModal('newFolderModal');
        document.getElementById('folderName').value = '';
        document.getElementById('folderName').focus();
    });

    // Remote toolbar: Upload to Remote
    document.getElementById('remoteUploadBtn').addEventListener('click', () => {
        if (!state.activeTabPeer) return;
        openModal('uploadModal');
        document.getElementById('uploadFileList').innerHTML = '';
        state.uploadFiles = [];
        document.getElementById('startUploadBtn').disabled = true;
        // Mark upload as "to remote" — handled in the upload start handler
        document.getElementById('uploadModal').dataset.remoteUploadPeer = state.activeTabPeer;
        const tab = state.remoteTabs[state.activeTabPeer];
        document.getElementById('uploadModal').dataset.remoteUploadPath = tab ? tab.currentPath : '';
    });

    // Remote toolbar: New Folder on remote
    document.getElementById('remoteNewFolderBtn').addEventListener('click', () => {
        if (!state.activeTabPeer) return;
        openModal('remoteNewFolderModal');
        document.getElementById('remoteFolderName').value = '';
        document.getElementById('remoteFolderName').focus();
    });

    // Remote New Folder confirm
    document.getElementById('confirmRemoteNewFolderBtn').addEventListener('click', remoteCreateFolder);

    // Remote Rename confirm
    document.getElementById('confirmRemoteRenameBtn').addEventListener('click', confirmRemoteRename);

    // Remote download button
    document.getElementById('newRemoteDownload').addEventListener('click', () => {
        openModal('remoteDownloadModal');
        document.getElementById('downloadUrl').value = '';
        // Show the actual destination so the user knows exactly where the
        // file will be saved (the folder they are currently browsing).
        const dest = state.currentPath || serverHome || '~';
        document.getElementById('downloadDestination').textContent = dest;
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

    // Compress confirm button
    const compressBtn = document.getElementById('confirmCompressBtn');
    if (compressBtn) {
        compressBtn.addEventListener('click', () => {
            confirmCompress();
        });
    }

    // Settings button
    const settingsBtn = document.getElementById('settingsBtn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            openSettingsModal();
        });
    }

    // Save settings button
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', () => {
            saveSettings();
        });
    }

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
            if (state.activeTabPeer) {
                remoteDeleteConfirm();
            } else {
                showDeleteConfirm();
            }
        } else if (e.key === 'F2' && state.selectedItem) {
            e.preventDefault();
            if (state.activeTabPeer) {
                showRemoteRenameDialog();
            } else {
                showRenameDialog();
            }
        } else if (e.key === 'F5') {
            e.preventDefault();
            if (state.activeTabPeer) {
                const tab = state.remoteTabs[state.activeTabPeer];
                browseRemoteDirectory(state.activeTabPeer, tab ? tab.currentPath : '');
            } else {
                browseDirectory(state.currentPath);
            }
            showToast('Refreshed', 'info');
        } else if (e.ctrlKey && e.key === 'c' && state.selectedItem && !state.activeTabPeer) {
            e.preventDefault();
            copyItem();
        } else if (e.ctrlKey && e.key === 'x' && state.selectedItem && !state.activeTabPeer) {
            e.preventDefault();
            cutItem();
        } else if (e.ctrlKey && e.key === 'v' && state.clipboard && !state.activeTabPeer) {
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
    // If a remote peer tab is active, route to the remote browser instead.
    if (state.activeTabPeer) {
        await browseRemoteDirectory(state.activeTabPeer, path);
        return;
    }
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
            updateOperationsPath(data.current_path);
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
            // Use viewport-relative coordinates because the menu uses
            // `position: fixed`. `pageX/pageY` would offset by the page
            // scroll and place the menu off-screen.
            showContextMenu(e.clientX, e.clientY);
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

    if (state.activeTabPeer) {
        if (isDir) {
            browseRemoteDirectory(state.activeTabPeer, path);
        } else {
            // In remote tab: offer to download the file to the local current path
            const peer = bridgeState.peers.find(p => p.id === state.activeTabPeer);
            const fileName = path.split('/').pop();
            if (confirm(`Download "${fileName}" from ${peer ? peer.name : 'remote'} to local "${state.currentPath}"?`)) {
                doRemoteFilePull(state.activeTabPeer, [path], state.currentPath);
            }
        }
        return;
    }

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

    // Sync both view-toggle button groups.
    ['gridViewBtn', 'remoteGridViewBtn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('active', mode === 'grid');
    });
    ['listViewBtn', 'remoteListViewBtn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('active', mode === 'list');
    });

    elements.fileList.classList.remove('grid-view', 'list-view');
    elements.fileList.classList.add(`${mode}-view`);

    // Re-render current directory.
    if (state.activeTabPeer) {
        const tab = state.remoteTabs[state.activeTabPeer];
        browseRemoteDirectory(state.activeTabPeer, tab ? tab.currentPath : '');
    } else {
        browseDirectory(state.currentPath);
    }
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

    // Show/hide the Extract item depending on whether the selected file is
    // a supported archive type.
    const extractBtn = document.getElementById('ctxExtract');
    if (extractBtn) {
        const item = state.selectedItem;
        const isArchive = item && !item.isDir && isExtractableFile(item.path || '');
        extractBtn.style.display = isArchive ? '' : 'none';
    }

    // Show first so we can measure the actual size.
    elements.contextMenu.style.left = `${x}px`;
    elements.contextMenu.style.top = `${y}px`;
    elements.contextMenu.classList.add('show');

    // Resolve the fixed header height from the CSS variable so the menu
    // can never slide behind it (a common problem when the user
    // right-clicks near the top of the page and the menu is tall enough
    // that the off-screen correction below would otherwise push it up
    // into / above the header).
    const headerHeightRaw = getComputedStyle(document.documentElement)
        .getPropertyValue('--header-height') || '60px';
    const headerHeight = parseInt(headerHeightRaw, 10) || 60;
    const margin = 8;

    const rect = elements.contextMenu.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let finalX = x;
    let finalY = y;

    // Horizontal: prefer flipping to the left if there isn't room on
    // the right, then clamp to the viewport.
    if (finalX + rect.width + margin > vw) {
        finalX = Math.max(margin, x - rect.width);
    }
    finalX = Math.max(margin, Math.min(finalX, vw - rect.width - margin));

    // Vertical: prefer flipping above the cursor if there isn't room
    // below, then clamp so the top stays below the header and the
    // bottom stays inside the viewport.
    if (finalY + rect.height + margin > vh) {
        finalY = y - rect.height;
    }
    const minTop = headerHeight + margin;
    const maxTop = Math.max(minTop, vh - rect.height - margin);
    finalY = Math.max(minTop, Math.min(finalY, maxTop));

    elements.contextMenu.style.left = `${finalX}px`;
    elements.contextMenu.style.top = `${finalY}px`;
}

function hideContextMenu() {
    elements.contextMenu.classList.remove('show');
}

function handleContextAction(action) {
    // When a remote peer tab is active, certain actions are intercepted and
    // proxied to the peer server; non-applicable local actions are ignored.
    if (state.activeTabPeer) {
        switch (action) {
            case 'open':
                if (!state.selectedItem) return;
                const remoteEl = document.querySelector(`.file-item[data-path="${CSS.escape(state.selectedItem.path)}"]`);
                if (remoteEl) openItem(remoteEl);
                break;
            case 'download':
                if (!state.selectedItem) return;
                doRemoteFilePull(state.activeTabPeer, [state.selectedItem.path], state.currentPath);
                break;
            case 'delete':
                if (!state.selectedItem) return;
                remoteDeleteConfirm();
                break;
            case 'rename':
                if (!state.selectedItem) return;
                showRemoteRenameDialog();
                break;
            case 'newfolder':
                openModal('remoteNewFolderModal');
                document.getElementById('remoteFolderName').value = '';
                document.getElementById('remoteFolderName').focus();
                break;
            case 'refresh': {
                const tab = state.remoteTabs[state.activeTabPeer];
                browseRemoteDirectory(state.activeTabPeer, tab ? tab.currentPath : '');
                showToast('Refreshed', 'info');
                break;
            }
            case 'bridge-send':
                // In remote tab, "Send to Server" sends a remote file to ANOTHER peer.
                // Skip — not meaningful in this context.
                showToast('Switch to Local tab to send local files to a server.', 'info');
                break;
            default:
                // Silently skip local-only actions (copy, cut, paste, compress, etc.)
                break;
        }
        return;
    }

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
        case 'compress':
            if (!state.selectedItem) return;
            showCompressDialog();
            break;
        case 'extract':
            if (!state.selectedItem) return;
            startExtraction(state.selectedItem.path);
            break;
        case 'bridge-send':
            handleBridgeSend();
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

// =============================================================
// Transfer Center
// =============================================================
//
// All uploads, local downloads, and remote downloads flow through
// `state.transfers` and are rendered both in the centered Transfer
// Center panel and (in compact form) in the sidebar's "Active
// Transfers" section. Each entry has the shape:
//
//     {
//         id: '<uuid>',
//         kind: 'upload' | 'download' | 'remote-download',
//         filename: 'foo.bin',
//         status: 'uploading' | 'downloading' | 'paused'
//                | 'cancelling' | 'cancelled' | 'completed' | 'error',
//         transferred: <int bytes>,
//         total: <int bytes>,            // 0 if unknown
//         speed: <int bytes/sec>,
//         error: <string>,
//         // kind-specific control hooks installed by the starter:
//         pause:    function() {},
//         resume:   function() {},
//         cancel:   function() {},
//         // transient runtime data:
//         _xhr:     XMLHttpRequest        // for uploads / local DLs
//         _abortController: AbortController
//     }
// =============================================================

const TERMINAL_STATUSES = ['completed', 'error', 'cancelled'];
const ACTIVE_STATUSES = ['uploading', 'downloading', 'paused', 'cancelling', 'pending'];

function setupTransferCenter() {
    document.getElementById('transferMinimizeBtn').addEventListener('click', () => {
        state.transferPanelMinimized = true;
        elements.transferCenter.classList.add('hidden');
        updateTransferReopen();
    });
    document.getElementById('transferCloseBtn').addEventListener('click', () => {
        // Close just hides the panel; the transfers themselves keep
        // running and stay accessible from the sidebar. The user must
        // click Cancel on a row to actually abort a transfer.
        state.transferPanelHidden = true;
        state.transferPanelMinimized = false;
        elements.transferCenter.classList.add('hidden');
        updateTransferReopen();
    });
    document.getElementById('transferClearBtn').addEventListener('click', () => {
        Object.values(state.transfers)
            .filter(t => TERMINAL_STATUSES.includes(t.status))
            .forEach(t => removeTransfer(t.id));
        renderTransfers();
    });
    elements.transferReopenBtn.addEventListener('click', () => {
        showTransferCenter();
    });
    document.getElementById('sidebarTransferExpand').addEventListener('click', () => {
        showTransferCenter();
    });
}

function showTransferCenter() {
    state.transferPanelHidden = false;
    state.transferPanelMinimized = false;
    elements.transferCenter.classList.remove('hidden');
    updateTransferReopen();
}

function updateTransferReopen() {
    const active = Object.values(state.transfers).filter(t =>
        ACTIVE_STATUSES.includes(t.status)
    ).length;
    if ((state.transferPanelHidden || state.transferPanelMinimized) && active > 0) {
        elements.transferReopenBtn.classList.remove('hidden');
        elements.transferReopenLabel.textContent = String(active);
    } else {
        elements.transferReopenBtn.classList.add('hidden');
    }
}

function addTransfer(transfer) {
    state.transfers[transfer.id] = transfer;
    // Auto-show the panel the first time something happens, unless the
    // user has explicitly closed or minimised it during this session.
    if (state.transferPanelHidden && !state.transferPanelMinimized) {
        showTransferCenter();
    }
    renderTransfers();
}

function updateTransfer(id, updates) {
    const t = state.transfers[id];
    if (!t) return;
    Object.assign(t, updates);
    renderTransfers();
}

function removeTransfer(id) {
    delete state.transfers[id];
}

function transferActionLabel(action) {
    return ({
        pause:   '<i class="fas fa-pause"></i> Pause',
        resume:  '<i class="fas fa-play"></i> Resume',
        cancel:  '<i class="fas fa-stop"></i> Cancel',
        dismiss: '<i class="fas fa-times"></i> Dismiss',
        retry:   '<i class="fas fa-redo"></i> Retry'
    })[action] || action;
}

function transferActionsFor(t) {
    const actions = [];
    if (t.status === 'uploading' || t.status === 'downloading' || t.status === 'running') {
        if (typeof t.pause === 'function') actions.push('pause');
        if (typeof t.cancel === 'function') actions.push('cancel');
    } else if (t.status === 'paused') {
        if (typeof t.resume === 'function') actions.push('resume');
        if (typeof t.cancel === 'function') actions.push('cancel');
    } else if (t.status === 'pending' || t.status === 'cancelling') {
        if (typeof t.cancel === 'function') actions.push('cancel');
    } else {
        // Terminal states: completed / error / cancelled.
        if (t.status === 'error' && typeof t.resume === 'function') {
            actions.push('retry');
        }
        actions.push('dismiss');
    }
    return actions;
}

async function dispatchTransferAction(id, action) {
    const t = state.transfers[id];
    if (!t) return;
    if (action === 'dismiss') {
        // Run any kind-specific dismiss hook (e.g. for remote downloads
        // we tell the server to forget the task) before removing the
        // local record, so that the next poll does not re-add it.
        if (typeof t.dismiss === 'function') {
            try { await t.dismiss(); } catch (e) { /* ignore */ }
        }
        removeTransfer(t.id);
        renderTransfers();
        return;
    }
    if (action === 'retry' && typeof t.resume === 'function') {
        try { t.resume(); } catch (e) { showToast('Retry failed: ' + e.message, 'error'); }
        return;
    }
    const fn = t[action];
    if (typeof fn === 'function') {
        try { fn(); } catch (e) { showToast('Action failed: ' + e.message, 'error'); }
    }
}

function transferKindIcon(kind) {
    return {
        upload: 'fa-upload',
        download: 'fa-download',
        'remote-download': 'fa-cloud-download-alt',
        compress: 'fa-file-archive',
        extract: 'fa-box-open'
    }[kind] || 'fa-exchange-alt';
}

function renderTransfers() {
    const transfers = Object.values(state.transfers).sort(
        (a, b) => (b.startedAt || 0) - (a.startedAt || 0)
    );
    const activeCount = transfers.filter(t => ACTIVE_STATUSES.includes(t.status)).length;

    if (elements.transferCountBadge) {
        elements.transferCountBadge.textContent = String(transfers.length);
    }
    if (elements.opQueue) {
        elements.opQueue.textContent = `${activeCount} active`;
    }

    // Centered panel
    if (elements.transferList && elements.transferEmpty) {
        if (!transfers.length) {
            elements.transferEmpty.style.display = '';
            elements.transferList.innerHTML = '';
        } else {
            elements.transferEmpty.style.display = 'none';
            elements.transferList.innerHTML = transfers.map(renderTransferRow).join('');
            attachTransferActionListeners(elements.transferList);
        }
    }

    // Sidebar compact view
    if (elements.sidebarTransfers) {
        if (!transfers.length) {
            elements.sidebarTransfers.innerHTML = '<p class="sidebar-empty">No active transfers</p>';
        } else {
            elements.sidebarTransfers.innerHTML = transfers.map(renderSidebarTransferRow).join('');
            attachTransferActionListeners(elements.sidebarTransfers);
        }
    }

    updateTransferReopen();
}

function transferProgressPct(t) {
    if (t.total > 0) {
        return Math.min(100, Math.max(0, (t.transferred / t.total) * 100));
    }
    return t.status === 'completed' ? 100 : 0;
}

function renderTransferRow(t) {
    const pct = transferProgressPct(t);
    const actions = transferActionsFor(t);
    const totalLabel = t.total > 0 ? formatSize(t.total) : 'Unknown';
    const speed = (t.status === 'uploading' || t.status === 'downloading' || t.status === 'running')
        ? `${formatSize(t.speed || 0)}/s`
        : (t.status === 'paused' ? 'Paused' : '');
    const errorLine = t.error
        ? `<span class="err-msg" title="${escapeHtml(t.error)}">${escapeHtml(t.error)}</span>`
        : '';
    return `
        <div class="transfer-row ${escapeHtml(t.status)}" data-id="${escapeHtml(t.id)}">
            <div class="transfer-row-head">
                <div class="transfer-row-name">
                    <i class="fas ${transferKindIcon(t.kind)}"></i>
                    <span class="filename" title="${escapeHtml(t.filename)}">${escapeHtml(t.filename)}</span>
                </div>
                <span class="transfer-row-status ${escapeHtml(t.status)}">${escapeHtml(t.status)}</span>
            </div>
            <div class="transfer-row-progress">
                <div class="transfer-row-progress-bar" style="width:${pct.toFixed(1)}%"></div>
            </div>
            <div class="transfer-row-info">
                <span>${formatSize(t.transferred || 0)} / ${totalLabel}</span>
                <span>${escapeHtml(speed)}</span>
                ${errorLine}
            </div>
            <div class="transfer-row-actions">
                ${actions.map(a =>
                    `<button class="btn ${a === 'cancel' ? 'btn-danger' : 'btn-secondary'}" data-action="${a}" data-id="${escapeHtml(t.id)}">${transferActionLabel(a)}</button>`
                ).join('')}
            </div>
        </div>
    `;
}

function renderSidebarTransferRow(t) {
    const pct = transferProgressPct(t);
    const actions = transferActionsFor(t);
    return `
        <div class="sidebar-transfer-row ${escapeHtml(t.status)}" data-id="${escapeHtml(t.id)}">
            <div class="head">
                <i class="fas ${transferKindIcon(t.kind)}"></i>
                <span class="name" title="${escapeHtml(t.filename)}">${escapeHtml(t.filename)}</span>
                <span class="pct">${pct.toFixed(0)}%</span>
            </div>
            <div class="bar"><span style="width:${pct.toFixed(1)}%"></span></div>
            <div class="actions">
                ${actions.map(a =>
                    `<button class="${a === 'cancel' ? 'danger' : ''}" data-action="${a}" data-id="${escapeHtml(t.id)}" title="${a}"><i class="fas ${({pause:'fa-pause',resume:'fa-play',cancel:'fa-stop',dismiss:'fa-times',retry:'fa-redo'})[a]}"></i></button>`
                ).join('')}
            </div>
        </div>
    `;
}

function attachTransferActionListeners(root) {
    root.querySelectorAll('button[data-action][data-id]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            dispatchTransferAction(btn.dataset.id, btn.dataset.action);
        });
    });
}

// =============================================================
// Local file download (with pause / resume / cancel via Range)
// =============================================================
function downloadSelectedItem() {
    if (!state.selectedItem) return;
    startManagedDownload(state.selectedItem.path, state.selectedItem.name || '');
}

async function startManagedDownload(serverPath, suggestedName) {
    const id = 'dl-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    const filename = suggestedName || serverPath.split('/').pop() || 'download';

    const transfer = {
        id,
        kind: 'download',
        filename,
        status: 'pending',
        transferred: 0,
        total: 0,
        speed: 0,
        startedAt: Date.now(),
        _abortController: null,
        _chunks: [],
        _serverPath: serverPath
    };

    transfer.cancel = () => {
        if (transfer._abortController) transfer._abortController.abort();
        transfer.status = 'cancelled';
        transfer._chunks = [];
        renderTransfers();
    };
    transfer.pause = () => {
        if (transfer.status !== 'downloading') return;
        if (transfer._abortController) transfer._abortController.abort();
        transfer.status = 'paused';
        renderTransfers();
    };
    transfer.resume = () => {
        if (transfer.status !== 'paused' && transfer.status !== 'error') return;
        runDownload(transfer);
    };

    addTransfer(transfer);
    runDownload(transfer);
}

async function runDownload(transfer) {
    transfer.status = 'downloading';
    transfer.error = null;
    transfer._abortController = new AbortController();
    renderTransfers();

    const url = `/api/download?path=${encodeURIComponent(transfer._serverPath)}`;

    try {
        const headers = {};
        if (transfer.transferred > 0) {
            headers['Range'] = `bytes=${transfer.transferred}-`;
        }
        const response = await fetch(url, {
            headers,
            signal: transfer._abortController.signal
        });

        if (!response.ok && response.status !== 206) {
            throw new Error(`Server responded with ${response.status}`);
        }

        // If we asked for a Range but the server returned 200, restart.
        const rangeHonoured = response.status === 206;
        if (transfer.transferred > 0 && !rangeHonoured) {
            transfer._chunks = [];
            transfer.transferred = 0;
        }

        // Determine total size from headers.
        if (rangeHonoured) {
            const cr = response.headers.get('Content-Range');
            if (cr) {
                const m = /\/(\d+)$/.exec(cr);
                if (m) transfer.total = parseInt(m[1], 10);
            }
        } else {
            const lenHeader = response.headers.get('Content-Length');
            if (lenHeader) transfer.total = parseInt(lenHeader, 10);
        }

        // Try to refine the suggested filename from Content-Disposition.
        const cd = response.headers.get('Content-Disposition');
        if (cd) {
            const m = /filename\*?=(?:UTF-8''|")?([^";]+)"?/i.exec(cd);
            if (m) {
                try { transfer.filename = decodeURIComponent(m[1]); }
                catch (e) { transfer.filename = m[1]; }
            }
        }

        const reader = response.body.getReader();
        const start = Date.now();
        const baseTransferred = transfer.transferred;
        let receivedSinceStart = 0;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            transfer._chunks.push(value);
            transfer.transferred += value.length;
            receivedSinceStart += value.length;
            const elapsed = (Date.now() - start) / 1000;
            transfer.speed = elapsed > 0 ? receivedSinceStart / elapsed : 0;
            renderTransfers();
        }

        // Stitch into a single Blob and trigger the browser save.
        const blob = new Blob(transfer._chunks);
        transfer._chunks = [];
        transfer.status = 'completed';
        transfer.speed = 0;
        renderTransfers();

        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = transfer.filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            URL.revokeObjectURL(a.href);
            document.body.removeChild(a);
        }, 0);
    } catch (err) {
        if (err.name === 'AbortError') {
            // status was already set by pause()/cancel()
            return;
        }
        transfer.status = 'error';
        transfer.error = err.message || String(err);
        renderTransfers();
        showToast(`Download failed: ${transfer.error}`, 'error');
    }
}

// =============================================================
// Resumable, chunked upload
// =============================================================
const UPLOAD_CHUNK_SIZE = 4 * 1024 * 1024;  // 4 MiB

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

    document.querySelectorAll('.remove-file').forEach(btn => {
        btn.addEventListener('click', () => {
            state.uploadFiles.splice(parseInt(btn.dataset.index), 1);
            handleFileSelection(state.uploadFiles);
        });
    });
}

function uploadFiles() {
    if (state.uploadFiles.length === 0) return;

    const modal = document.getElementById('uploadModal');
    const remoteUploadPeer = modal.dataset.remoteUploadPeer || '';
    const remoteUploadPath = modal.dataset.remoteUploadPath || '';
    delete modal.dataset.remoteUploadPeer;
    delete modal.dataset.remoteUploadPath;

    const filesToUpload = state.uploadFiles.slice();
    state.uploadFiles = [];
    closeModal('uploadModal');

    // Upload to local server first; if a remote target is set, each
    // transfer will automatically push to the peer once it completes.
    const localDest = state.currentPath;
    filesToUpload.forEach(file => {
        const transfer = startManagedUpload(file, localDest);
        if (remoteUploadPeer && remoteUploadPath) {
            transfer._remoteUploadTarget = { peerId: remoteUploadPeer, remotePath: remoteUploadPath };
        }
    });
    showTransferCenter();
}

async function startManagedUpload(file, destPath) {
    const id = 'up-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
    const transfer = {
        id,
        kind: 'upload',
        filename: file.name,
        status: 'pending',
        transferred: 0,
        total: file.size,
        speed: 0,
        startedAt: Date.now(),
        _file: file,
        _destPath: destPath,
        _uploadId: null,
        _xhr: null,
        _pauseRequested: false,
        _cancelRequested: false,
        _remoteUploadTarget: null  // set by uploadFiles() for "Upload to Remote" flow
    };

    transfer.pause = () => {
        transfer._pauseRequested = true;
        if (transfer._xhr) transfer._xhr.abort();
        if (transfer.status === 'uploading') {
            transfer.status = 'paused';
            renderTransfers();
        }
    };
    transfer.resume = () => {
        if (transfer.status !== 'paused' && transfer.status !== 'error') return;
        transfer._pauseRequested = false;
        runUpload(transfer);
    };
    transfer.cancel = async () => {
        transfer._cancelRequested = true;
        transfer._pauseRequested = false;
        if (transfer._xhr) transfer._xhr.abort();
        transfer.status = 'cancelling';
        renderTransfers();
        if (transfer._uploadId) {
            try {
                await fetch(`/api/upload-cancel/${transfer._uploadId}`, { method: 'DELETE' });
            } catch (e) { /* ignore */ }
        }
        transfer.status = 'cancelled';
        renderTransfers();
    };

    addTransfer(transfer);

    // Return immediately so the caller can attach metadata (e.g.
    // _remoteUploadTarget) before the async upload sequence begins.
    setTimeout(async () => {
        try {
            const initResponse = await fetch('/api/upload-init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: file.name,
                    path: destPath,
                    size: file.size
                })
            });
            const initData = await initResponse.json();
            if (!initResponse.ok) {
                throw new Error(initData.error || 'Failed to start upload');
            }
            transfer._uploadId = initData.upload_id;
            transfer.filename = initData.filename || transfer.filename;
        } catch (err) {
            transfer.status = 'error';
            transfer.error = err.message;
            renderTransfers();
            showToast(`Upload failed to start: ${err.message}`, 'error');
            return;
        }
        runUpload(transfer);
    }, 0);

    return transfer;
}

function sendChunk(transfer, chunk, start, total) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        transfer._xhr = xhr;
        xhr.open('PUT', `/api/upload-chunk/${transfer._uploadId}`);
        xhr.setRequestHeader(
            'Content-Range',
            `bytes ${start}-${start + chunk.size - 1}/${total}`
        );
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');
        const startTime = Date.now();
        xhr.upload.onprogress = (e) => {
            if (!e.lengthComputable) return;
            transfer.transferred = start + e.loaded;
            const elapsed = (Date.now() - startTime) / 1000;
            transfer.speed = elapsed > 0 ? e.loaded / elapsed : 0;
            renderTransfers();
        };
        xhr.onload = () => {
            transfer._xhr = null;
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(JSON.parse(xhr.responseText || '{}'));
            } else {
                let msg = `HTTP ${xhr.status}`;
                try { msg = JSON.parse(xhr.responseText).error || msg; } catch (e) {}
                reject(new Error(msg));
            }
        };
        xhr.onerror = () => {
            transfer._xhr = null;
            reject(new Error('Network error during upload'));
        };
        xhr.onabort = () => {
            transfer._xhr = null;
            reject(Object.assign(new Error('aborted'), { aborted: true }));
        };
        xhr.send(chunk);
    });
}

async function runUpload(transfer) {
    transfer.status = 'uploading';
    transfer.error = null;
    renderTransfers();

    // Resume from server-known offset if we have an upload session.
    try {
        if (transfer._uploadId) {
            const status = await fetch(`/api/upload-status/${transfer._uploadId}`);
            if (status.ok) {
                const data = await status.json();
                transfer.transferred = data.received || 0;
            }
        }
    } catch (e) { /* ignore */ }

    const file = transfer._file;
    let offset = transfer.transferred;
    while (offset < file.size) {
        if (transfer._cancelRequested) return;
        if (transfer._pauseRequested) {
            transfer.status = 'paused';
            renderTransfers();
            return;
        }
        const end = Math.min(offset + UPLOAD_CHUNK_SIZE, file.size);
        const chunk = file.slice(offset, end);
        try {
            const result = await sendChunk(transfer, chunk, offset, file.size);
            offset = result.received;
            transfer.transferred = offset;
            renderTransfers();
        } catch (err) {
            if (err.aborted) {
                // pause/cancel already updated the status
                return;
            }
            transfer.status = 'error';
            transfer.error = err.message;
            transfer.speed = 0;
            renderTransfers();
            showToast(`Upload error: ${err.message}`, 'error');
            return;
        }
    }

    try {
        const completeResponse = await fetch(`/api/upload-complete/${transfer._uploadId}`, {
            method: 'POST'
        });
        const data = await completeResponse.json();
        if (!completeResponse.ok) {
            throw new Error(data.error || 'Failed to finalise upload');
        }
        transfer.status = 'completed';
        transfer.speed = 0;
        transfer.transferred = transfer.total;
        renderTransfers();
        // Refresh the directory listing if we uploaded into the
        // currently-displayed directory.
        if (transfer._destPath === state.currentPath) {
            browseDirectory(state.currentPath);
        }
        // If this was an "Upload to Remote" operation, automatically push the
        // newly-uploaded local file to the remote peer.
        if (transfer._remoteUploadTarget) {
            const { peerId, remotePath } = transfer._remoteUploadTarget;
            const localPath = transfer._destPath.replace(/\/+$/, '') + '/' + transfer.filename;
            await fetch('/api/bridge/push', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    peer_id: peerId,
                    files: [localPath],
                    destination: remotePath,
                }),
            }).then(r => r.json()).then(data => {
                if (data.task_id) {
                    showToast('Pushing to remote server…', 'info');
                    showTransferCenter();
                }
            }).catch(() => {});
        }
    } catch (err) {
        transfer.status = 'error';
        transfer.error = err.message;
        renderTransfers();
        showToast(`Upload finalisation failed: ${err.message}`, 'error');
    }
}

// =============================================================
// Remote downloads (server-side)
// =============================================================
async function startRemoteDownload() {
    const rawUrls = document.getElementById('downloadUrl').value.trim();
    const urls = rawUrls
        .split(/\r?\n|,/)
        .map(url => url.trim())
        .filter(Boolean);

    if (!urls.length) {
        showToast('Please enter at least one URL', 'warning');
        return;
    }

    for (const url of urls) {
        try {
            const parsedUrl = new URL(url);
            if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
                showToast('Only HTTP and HTTPS URLs are supported', 'error');
                return;
            }
        } catch (e) {
            showToast('Invalid URL format: ' + url, 'error');
            return;
        }
    }

    const destination = state.currentPath || serverHome || '~';

    showLoading();
    try {
        const response = await fetch('/api/remote-download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls, destination })
        });
        const data = await response.json();
        if (response.ok) {
            const count = data.count || (data.task_ids ? data.task_ids.length : 1);
            showToast(`Started ${count} download(s)`, 'success');
            document.getElementById('downloadUrl').value = '';
            closeModal('remoteDownloadModal');
            // Show transfer center so the user sees progress immediately.
            showTransferCenter();
            setTimeout(refreshRemoteDownloads, 300);
        } else {
            showToast(data.error || 'Failed to start download', 'error');
        }
    } catch (error) {
        console.error('Remote download error:', error);
        showToast('Network error: ' + error.message, 'error');
    }
    hideLoading();
}

async function refreshRemoteDownloads() {
    let tasks;
    try {
        const response = await fetch('/api/download-tasks');
        if (!response.ok) return;
        tasks = await response.json();
    } catch (err) {
        return;
    }
    if (!Array.isArray(tasks)) return;

    const seenIds = new Set();
    tasks.forEach(task => {
        const id = 'rd-' + task.id;
        seenIds.add(id);
        let transfer = state.transfers[id];
        if (!transfer) {
            transfer = makeRemoteDownloadTransfer(id, task);
            state.transfers[id] = transfer;
        }
        // Map server status -> transfer status.
        let status = task.status;
        if (status === 'pending') status = 'downloading';
        transfer.status = status;
        transfer.transferred = task.downloaded || 0;
        transfer.total = task.total_size || 0;
        transfer.speed = task.speed || 0;
        transfer.error = task.error || null;
        transfer.filename = task.filename || transfer.filename || task.url;
    });

    // Drop entries for remote-download tasks that the server forgot
    // about (e.g. dismissed). Local upload/download transfers are kept.
    Object.keys(state.transfers).forEach(id => {
        if (id.startsWith('rd-') && !seenIds.has(id)) {
            delete state.transfers[id];
        }
    });

    renderTransfers();
}

function makeRemoteDownloadTransfer(id, task) {
    const taskId = task.id;
    const transfer = {
        id,
        kind: 'remote-download',
        filename: task.filename || task.url || 'remote download',
        status: task.status,
        transferred: task.downloaded || 0,
        total: task.total_size || 0,
        speed: task.speed || 0,
        error: task.error || null,
        startedAt: (task.created_at || Date.now() / 1000) * 1000,
        _serverTaskId: taskId
    };
    transfer.cancel = async () => {
        try {
            await fetch(`/api/cancel-download/${taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
        refreshRemoteDownloads();
    };
    transfer.pause = async () => {
        try {
            await fetch(`/api/pause-download/${taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
        refreshRemoteDownloads();
    };
    transfer.resume = async () => {
        try {
            await fetch(`/api/resume-download/${taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
        refreshRemoteDownloads();
    };
    transfer.dismiss = async () => {
        try {
            await fetch(`/api/dismiss-download/${taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
    };
    return transfer;
}

// =============================================================
// Compress endpoint integration
// =============================================================
function showCompressDialog() {
    const target = state.selectedItem;
    if (!target) return;
    const sources = [target.path];
    document.getElementById('compressSourcesList').innerHTML = sources.map(p => `
        <div class="item"><i class="fas fa-file-archive"></i> ${escapeHtml(p)}</div>
    `).join('');
    const baseName = (target.name || 'archive').replace(/\.[^.]+$/, '');
    document.getElementById('compressName').value = baseName || 'archive';
    document.getElementById('compressFormat').value = 'zip';
    openModal('compressModal');
}

async function confirmCompress() {
    const target = state.selectedItem;
    if (!target) return;
    const name = document.getElementById('compressName').value.trim();
    const format = document.getElementById('compressFormat').value;

    let response, data;
    try {
        response = await fetch('/api/compress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sources: [target.path],
                destination: state.currentPath,
                name,
                format
            })
        });
        data = await response.json();
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
        return;
    }

    if (!response.ok || !data.task_id) {
        showToast(data && data.error ? data.error : 'Compression failed', 'error');
        return;
    }

    // Compression now runs in the background on the server. Register a
    // transfer in the transfer center and poll the progress endpoint so
    // the user gets a real progress bar instead of an opaque spinner.
    closeModal('compressModal');
    startCompressionTransfer(data);
}

const COMPRESS_PROGRESS_POLL_MS = 750;

function startCompressionTransfer(initial) {
    const id = 'cmp-' + initial.task_id;
    const transfer = {
        id,
        kind: 'compress',
        filename: initial.name || 'archive',
        status: 'running',
        transferred: 0,
        total: initial.total_size || 0,
        speed: 0,
        startedAt: Date.now(),
        _taskId: initial.task_id,
        _format: initial.format || ''
    };
    transfer.cancel = async () => {
        try {
            await fetch(`/api/cancel-compress/${transfer._taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
    };
    addTransfer(transfer);
    showTransferCenter();
    pollCompressionTransfer(transfer);
}

async function pollCompressionTransfer(transfer) {
    let lastProcessed = 0;
    let lastTimestamp = Date.now();
    while (true) {
        let resp;
        try {
            resp = await fetch(`/api/compress-progress/${transfer._taskId}`);
        } catch (e) {
            transfer.status = 'error';
            transfer.error = 'Lost connection to server';
            renderTransfers();
            return;
        }
        if (!resp.ok) {
            transfer.status = 'error';
            transfer.error = `Server responded with ${resp.status}`;
            renderTransfers();
            return;
        }
        const info = await resp.json();
        transfer.total = info.total_size || transfer.total;
        transfer.transferred = info.processed_size || 0;
        transfer.filename = info.name || transfer.filename;
        transfer._currentFile = info.current_file || '';

        const now = Date.now();
        const elapsed = (now - lastTimestamp) / 1000;
        if (elapsed > 0.25) {
            transfer.speed = (transfer.transferred - lastProcessed) / elapsed;
            lastProcessed = transfer.transferred;
            lastTimestamp = now;
        }

        if (info.status === 'completed') {
            transfer.status = 'completed';
            transfer.transferred = info.size || transfer.total || transfer.transferred;
            transfer.total = transfer.transferred || transfer.total;
            transfer.speed = 0;
            renderTransfers();
            const sizeLabel = info.size_formatted || formatSize(transfer.transferred);
            showToast(`Created ${transfer.filename} (${sizeLabel})`, 'success');
            browseDirectory(state.currentPath);
            return;
        }
        if (info.status === 'error') {
            transfer.status = 'error';
            transfer.error = info.error || 'Compression failed';
            transfer.speed = 0;
            renderTransfers();
            showToast(`Compression failed: ${transfer.error}`, 'error');
            return;
        }
        if (info.status === 'cancelled') {
            transfer.status = 'cancelled';
            transfer.speed = 0;
            renderTransfers();
            return;
        }
        // 'pending' / 'running' / 'cancelling'
        transfer.status = info.status === 'cancelling' ? 'cancelling' : 'running';
        renderTransfers();
        await new Promise(r => setTimeout(r, COMPRESS_PROGRESS_POLL_MS));
    }
}

// =============================================================
// Extract (decompress) endpoint integration
// =============================================================

const ARCHIVE_EXTENSIONS = new Set([
    '.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.gz', '.bz2', '.xz'
]);

function isExtractableFile(path) {
    const lower = (path || '').toLowerCase();
    if (lower.endsWith('.tar.gz') || lower.endsWith('.tar.bz2') || lower.endsWith('.tar.xz')) {
        return true;
    }
    const dot = lower.lastIndexOf('.');
    return dot !== -1 && ARCHIVE_EXTENSIONS.has(lower.slice(dot));
}

async function startExtraction(archivePath) {
    if (!archivePath) return;

    let response, data;
    try {
        response = await fetch('/api/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: archivePath })
        });
        data = await response.json();
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
        return;
    }

    if (!response.ok || !data.task_id) {
        showToast(data && data.error ? data.error : 'Extraction failed to start', 'error');
        return;
    }

    startExtractionTransfer(data);
}

const EXTRACT_PROGRESS_POLL_MS = 750;

function startExtractionTransfer(initial) {
    const id = 'ext-' + initial.task_id;
    const transfer = {
        id,
        kind: 'extract',
        filename: initial.archive || 'archive',
        status: 'running',
        transferred: 0,
        total: initial.total_size || 0,
        speed: 0,
        startedAt: Date.now(),
        _taskId: initial.task_id,
    };
    transfer.cancel = async () => {
        try {
            await fetch(`/api/cancel-extract/${transfer._taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
    };
    addTransfer(transfer);
    showTransferCenter();
    pollExtractionTransfer(transfer);
}

async function pollExtractionTransfer(transfer) {
    let lastExtracted = 0;
    let lastTimestamp = Date.now();
    while (true) {
        let resp;
        try {
            resp = await fetch(`/api/extract-progress/${transfer._taskId}`);
        } catch (e) {
            transfer.status = 'error';
            transfer.error = 'Lost connection to server';
            renderTransfers();
            return;
        }
        if (!resp.ok) {
            transfer.status = 'error';
            transfer.error = `Server responded with ${resp.status}`;
            renderTransfers();
            return;
        }
        const info = await resp.json();
        transfer.total = info.total_size || transfer.total;
        transfer.transferred = info.extracted_size || 0;
        transfer._currentFile = info.current_file || '';

        const now = Date.now();
        const elapsed = (now - lastTimestamp) / 1000;
        if (elapsed > 0.25) {
            transfer.speed = (transfer.transferred - lastExtracted) / elapsed;
            lastExtracted = transfer.transferred;
            lastTimestamp = now;
        }

        if (info.status === 'completed') {
            transfer.status = 'completed';
            transfer.transferred = info.extracted_size || transfer.total || transfer.transferred;
            transfer.total = transfer.transferred || transfer.total;
            transfer.speed = 0;
            renderTransfers();
            const files = info.extracted_files || 0;
            showToast(`Extracted ${files} file(s) to ${info.destination || 'same folder'}`, 'success');
            browseDirectory(state.currentPath);
            return;
        }
        if (info.status === 'error') {
            transfer.status = 'error';
            transfer.error = info.error || 'Extraction failed';
            transfer.speed = 0;
            renderTransfers();
            showToast(`Extraction failed: ${transfer.error}`, 'error');
            return;
        }
        if (info.status === 'cancelled') {
            transfer.status = 'cancelled';
            transfer.speed = 0;
            renderTransfers();
            return;
        }
        transfer.status = info.status === 'cancelling' ? 'cancelling' : 'running';
        renderTransfers();
        await new Promise(r => setTimeout(r, EXTRACT_PROGRESS_POLL_MS));
    }
}

// =============================================================
// Settings modal
// =============================================================

async function openSettingsModal() {
    try {
        const resp = await fetch('/api/settings');
        if (resp.ok) {
            const s = await resp.json();
            document.getElementById('settingsHost').value = s.host || '';
            document.getElementById('settingsPort').value = s.port || '';
            document.getElementById('settingsRootDir').value = s.root_directory || '';
            document.getElementById('settingsMaxUpload').value = s.max_upload_size || '';
            document.getElementById('settingsRead').checked = !!s.read_permission;
            document.getElementById('settingsWrite').checked = !!s.write_permission;
            document.getElementById('settingsDelete').checked = !!s.delete_permission;
        }
    } catch (e) { /* show modal even if we couldn't fetch */ }
    openModal('settingsModal');
}

async function saveSettings() {
    const payload = {
        host: document.getElementById('settingsHost').value.trim(),
        port: parseInt(document.getElementById('settingsPort').value, 10) || undefined,
        root_directory: document.getElementById('settingsRootDir').value.trim(),
        max_upload_size: parseInt(document.getElementById('settingsMaxUpload').value, 10) || undefined,
        read_permission: document.getElementById('settingsRead').checked,
        write_permission: document.getElementById('settingsWrite').checked,
        delete_permission: document.getElementById('settingsDelete').checked,
    };
    // Remove undefined values
    Object.keys(payload).forEach(k => payload[k] === undefined && delete payload[k]);

    try {
        const resp = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (resp.ok) {
            showToast('Settings saved successfully', 'success');
            closeModal('settingsModal');
        } else {
            showToast(data.error || 'Failed to save settings', 'error');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}

// =============================================================
// Server info (tunnel)
// =============================================================
async function loadServerInfo() {
    try {
        const response = await fetch('/api/server-info');
        if (!response.ok) return;
        const data = await response.json();
        renderTunnelInfo(data);
    } catch (e) { /* ignore */ }
}

function renderTunnelInfo(info) {
    if (!elements.tunnelSection || !elements.tunnelStatus || !elements.tunnelUrl) return;
    if (!info || info.tunnel_status === 'disabled') {
        elements.tunnelSection.style.display = 'none';
        return;
    }
    elements.tunnelSection.style.display = '';
    elements.tunnelStatus.className = 'tunnel-status ' + escapeHtml(info.tunnel_status);
    if (info.tunnel_status === 'active' && info.tunnel_url) {
        elements.tunnelStatus.textContent = 'Active';
        elements.tunnelUrl.textContent = info.tunnel_url;
        elements.tunnelUrl.href = info.tunnel_url;
    } else if (info.tunnel_status === 'starting') {
        elements.tunnelStatus.textContent = 'Starting...';
        elements.tunnelUrl.textContent = '';
        elements.tunnelUrl.removeAttribute('href');
    } else if (info.tunnel_status === 'error') {
        elements.tunnelStatus.textContent = 'Error';
        elements.tunnelUrl.textContent = info.tunnel_error || 'unknown error';
        elements.tunnelUrl.removeAttribute('href');
    }
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
            if (elements.opStorage) {
                elements.opStorage.textContent = `${Math.round(data.percent_used)}% used`;
            }
        }
    } catch (error) {
        console.error('Failed to load disk usage:', error);
    }
}

function updateOperationsClock() {
    if (!elements.opClock) return;

    const time = new Date().toISOString().slice(11, 19);
    elements.opClock.textContent = `UTC ${time}`;
}

function updateOperationsPath(path) {
    if (!elements.opPath) return;

    elements.opPath.textContent = `Path: ${path || 'pending'}`;
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

// =============================================================
// Peer Tabs  – connect / switch / browse remote server
// =============================================================

// ── Tab lifecycle ─────────────────────────────────────────────────────────

function addPeerTab(peer) {
    if (document.getElementById('tab-' + peer.id)) return; // already exists

    // Initialise per-peer browse state.
    if (!state.remoteTabs[peer.id]) {
        state.remoteTabs[peer.id] = { currentPath: '', selectedItem: null };
    }

    const tabBar = document.getElementById('tabBar');
    if (!tabBar) return;

    const tab = document.createElement('div');
    tab.className = 'tab';
    tab.id = 'tab-' + peer.id;
    tab.dataset.tab = peer.id;
    tab.innerHTML = `
        <i class="fas fa-server"></i>
        <span>${escapeHtml(peer.name)}</span>
        <span class="tab-close" title="Disconnect and close tab" data-peer-id="${escapeHtml(peer.id)}">
            <i class="fas fa-times"></i>
        </span>
    `;
    tab.addEventListener('click', (e) => {
        if (e.target.closest('.tab-close')) return; // handled separately
        switchToPeerTab(peer.id);
    });
    tab.querySelector('.tab-close').addEventListener('click', (e) => {
        e.stopPropagation();
        disconnectBridgePeer(peer.id);
    });

    tabBar.appendChild(tab);
    updatePeerBadge();
}

function removePeerTab(peerId) {
    const tab = document.getElementById('tab-' + peerId);
    if (tab) tab.remove();
    delete state.remoteTabs[peerId];

    // If the removed tab was active, switch to local.
    if (state.activeTabPeer === peerId) {
        switchToLocalTab();
    }
    updatePeerBadge();
}

function switchToLocalTab() {
    state.activeTabPeer = null;

    // Tab bar: deactivate all, activate local.
    document.querySelectorAll('#tabBar .tab').forEach(t => t.classList.remove('active'));
    const localTab = document.getElementById('tab-local');
    if (localTab) localTab.classList.add('active');

    // Toolbar: show local actions, hide remote.
    document.getElementById('localToolbarActions').classList.remove('hidden');
    document.getElementById('remoteToolbarActions').classList.add('hidden');

    // Restore local file list.
    browseDirectory(state.currentPath || serverHome || '~');
    updatePeerBadge();
}

function switchToPeerTab(peerId) {
    state.activeTabPeer = peerId;

    // Tab bar.
    document.querySelectorAll('#tabBar .tab').forEach(t => t.classList.remove('active'));
    const tab = document.getElementById('tab-' + peerId);
    if (tab) tab.classList.add('active');

    // Toolbar.
    document.getElementById('localToolbarActions').classList.add('hidden');
    document.getElementById('remoteToolbarActions').classList.remove('hidden');

    // Browse the remote server (starting from root or last known path).
    const peerTab = state.remoteTabs[peerId];
    browseRemoteDirectory(peerId, peerTab ? peerTab.currentPath : '');
    updatePeerBadge();
}

// ── Status bar peer badge ─────────────────────────────────────────────────

function updatePeerBadge() {
    const badge = elements.peerBadge;
    const badgeText = elements.peerBadgeText;
    if (!badge || !badgeText) return;

    const connected = bridgeState.peers || [];
    if (!connected.length) {
        badge.style.display = 'none';
        return;
    }

    badge.style.display = '';
    if (state.activeTabPeer) {
        const peer = connected.find(p => p.id === state.activeTabPeer);
        badgeText.textContent = `Browsing: ${peer ? peer.name : state.activeTabPeer}`;
    } else {
        const names = connected.map(p => p.name).join(', ');
        badgeText.textContent = `Connected to: ${names}`;
    }
}

// ── Remote directory browse ───────────────────────────────────────────────

async function browseRemoteDirectory(peerId, path) {
    showLoading();
    try {
        const params = new URLSearchParams({ peer_id: peerId });
        if (path) params.set('path', path);
        const resp = await fetch('/api/bridge/peer-browse?' + params);
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Remote browse failed', 'error');
            hideLoading();
            return;
        }

        const currentPath = data.current_path || path || '/';

        // Update per-peer tab state.
        if (!state.remoteTabs[peerId]) state.remoteTabs[peerId] = {};
        state.remoteTabs[peerId].currentPath = currentPath;

        // Render breadcrumb with remote prefix.
        renderRemoteBreadcrumb(peerId, currentPath, data.parent_path);

        // Render file list using the existing component.
        renderRemoteFileList(data.items || []);
        elements.itemCount.textContent = `${(data.items || []).length} items`;
        elements.statusText.textContent = 'Remote';

        clearSelection();
    } catch (e) {
        showToast('Network error while browsing remote', 'error');
    }
    hideLoading();
}

function renderRemoteBreadcrumb(peerId, path, parentPath) {
    const peer = bridgeState.peers.find(p => p.id === peerId);
    const peerName = peer ? peer.name : 'Remote';

    const parts = path.split('/').filter(p => p);
    let currentPath = '';

    let html = `<span class="breadcrumb-item" data-remote-peer="${escapeHtml(peerId)}" data-path="/">
        <i class="fas fa-server"></i>&thinsp;${escapeHtml(peerName)}
    </span>`;

    parts.forEach((part, index) => {
        currentPath += '/' + part;
        const isLast = index === parts.length - 1;
        html += `<span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-item ${isLast ? 'active' : ''}"
                  data-remote-peer="${escapeHtml(peerId)}"
                  data-path="${escapeHtml(currentPath)}">${escapeHtml(part)}</span>`;
    });

    elements.breadcrumb.innerHTML = html;

    elements.breadcrumb.querySelectorAll('.breadcrumb-item[data-remote-peer]').forEach(item => {
        item.addEventListener('click', () => {
            browseRemoteDirectory(item.dataset.remotePeer, item.dataset.path);
        });
    });
}

function renderRemoteFileList(items) {
    if (!items.length) {
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
            const icon = item.icon || (item.is_dir ? 'fa-folder' : 'fa-file');
            html += `<div class="file-item remote-file-item"
                          data-path="${escapeHtml(item.path)}"
                          data-is-dir="${item.is_dir}"
                          data-name="${escapeHtml(item.name)}">
                <i class="fas ${sanitizeIconClass(icon)} file-icon"></i>
                <span class="file-name">${escapeHtml(item.name)}</span>
            </div>`;
        });
    } else {
        items.forEach(item => {
            const icon = item.icon || (item.is_dir ? 'fa-folder' : 'fa-file');
            html += `<div class="file-item remote-file-item"
                          data-path="${escapeHtml(item.path)}"
                          data-is-dir="${item.is_dir}"
                          data-name="${escapeHtml(item.name)}">
                <i class="fas ${sanitizeIconClass(icon)} file-icon"></i>
                <span class="file-name">${escapeHtml(item.name)}</span>
                <span class="file-size">${item.size_formatted || ''}</span>
                <span class="file-modified">${item.modified || ''}</span>
                <span class="file-perms">${item.permissions || ''}</span>
            </div>`;
        });
    }

    elements.fileList.innerHTML = html;

    elements.fileList.querySelectorAll('.file-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            // Store selected item (same shape as local selectItem).
            clearSelection();
            item.classList.add('selected');
            state.selectedItem = {
                path: item.dataset.path,
                isDir: item.dataset.isDir === 'true',
                name: item.dataset.name,
            };
            if (state.activeTabPeer) {
                state.remoteTabs[state.activeTabPeer].selectedItem = state.selectedItem;
                showRemoteItemDetails(state.selectedItem);
            }
        });

        item.addEventListener('dblclick', () => {
            openItem(item);
        });

        item.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            // Re-use selectItem-equivalent above.
            clearSelection();
            item.classList.add('selected');
            state.selectedItem = {
                path: item.dataset.path,
                isDir: item.dataset.isDir === 'true',
                name: item.dataset.name,
            };
            if (state.activeTabPeer) {
                state.remoteTabs[state.activeTabPeer].selectedItem = state.selectedItem;
            }
            showContextMenu(e.clientX, e.clientY);
        });
    });
}

// Show a details panel for a remote item (no server round-trip needed
// because we already have all the metadata from the browse response).
function showRemoteItemDetails(item) {
    const peer = bridgeState.peers.find(p => p.id === state.activeTabPeer);
    const peerName = peer ? peer.name : 'Remote';
    const icon = item.isDir ? 'fa-folder' : 'fa-file';

    elements.detailsContent.innerHTML = `
        <div class="detail-preview">
            <i class="fas ${icon} file-icon" style="font-size:48px;color:var(--accent-primary);margin:16px 0;display:block;text-align:center;"></i>
        </div>
        <div class="detail-info">
            <div class="detail-name">${escapeHtml(item.name || item.path.split('/').pop())}</div>
            <div class="detail-row">
                <span class="label">Server</span>
                <span class="value">${escapeHtml(peerName)}</span>
            </div>
            <div class="detail-row">
                <span class="label">Path</span>
                <span class="value" style="word-break:break-all;font-size:11px;">${escapeHtml(item.path)}</span>
            </div>
        </div>
        ${!item.isDir ? `<div class="detail-actions">
            <button class="btn btn-primary btn-full" onclick="doRemoteFilePull(state.activeTabPeer, [state.selectedItem.path], state.currentPath)">
                <i class="fas fa-download"></i> Download to Local
            </button>
        </div>` : ''}
    `;
    elements.detailsPanel.classList.add('open');
}

// ── Remote file operations ────────────────────────────────────────────────

/** Pull remote file(s) to local destination — wrapper used by single-file download. */
async function doRemoteFilePull(peerId, remotePaths, localDest) {
    if (!peerId || !remotePaths.length || !localDest) {
        showToast('Missing parameters for download', 'warning');
        return;
    }
    showLoading();
    try {
        const resp = await fetch('/api/bridge/pull', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ peer_id: peerId, files: remotePaths, destination: localDest }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Download failed', 'error');
        } else {
            showToast('Download started', 'success');
            showTransferCenter();
        }
    } catch (e) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

function remoteDeleteConfirm() {
    if (!state.selectedItem) return;
    const name = state.selectedItem.name || state.selectedItem.path.split('/').pop();
    if (!confirm(`Delete "${name}" on the remote server? This cannot be undone.`)) return;
    remoteDelete();
}

async function remoteDelete() {
    if (!state.selectedItem || !state.activeTabPeer) return;
    showLoading();
    try {
        const resp = await fetch('/api/bridge/remote-op', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                peer_id: state.activeTabPeer,
                op: 'delete',
                payload: { path: state.selectedItem.path },
            }),
        });
        const data = await resp.json();
        if (resp.ok) {
            showToast('Deleted on remote server', 'success');
            clearSelection();
            const tab = state.remoteTabs[state.activeTabPeer];
            browseRemoteDirectory(state.activeTabPeer, tab ? tab.currentPath : '');
        } else {
            showToast(data.error || 'Delete failed', 'error');
        }
    } catch (e) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

function showRemoteRenameDialog() {
    if (!state.selectedItem) return;
    const name = state.selectedItem.name || state.selectedItem.path.split('/').pop();
    document.getElementById('remoteNewName').value = name;
    openModal('remoteRenameModal');
    document.getElementById('remoteNewName').focus();
    document.getElementById('remoteNewName').select();
}

async function confirmRemoteRename() {
    if (!state.selectedItem || !state.activeTabPeer) return;
    const newName = document.getElementById('remoteNewName').value.trim();
    if (!newName) { showToast('Enter a new name', 'warning'); return; }
    showLoading();
    try {
        const resp = await fetch('/api/bridge/remote-op', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                peer_id: state.activeTabPeer,
                op: 'rename',
                payload: { path: state.selectedItem.path, new_name: newName },
            }),
        });
        const data = await resp.json();
        if (resp.ok) {
            showToast('Renamed on remote server', 'success');
            closeModal('remoteRenameModal');
            clearSelection();
            const tab = state.remoteTabs[state.activeTabPeer];
            browseRemoteDirectory(state.activeTabPeer, tab ? tab.currentPath : '');
        } else {
            showToast(data.error || 'Rename failed', 'error');
        }
    } catch (e) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

async function remoteCreateFolder() {
    if (!state.activeTabPeer) return;
    const name = document.getElementById('remoteFolderName').value.trim();
    if (!name) { showToast('Enter a folder name', 'warning'); return; }
    const tab = state.remoteTabs[state.activeTabPeer];
    const remotePath = tab ? tab.currentPath : '';
    showLoading();
    try {
        const resp = await fetch('/api/bridge/remote-op', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                peer_id: state.activeTabPeer,
                op: 'create-folder',
                payload: { path: remotePath, name },
            }),
        });
        const data = await resp.json();
        if (resp.ok) {
            showToast('Folder created on remote server', 'success');
            closeModal('remoteNewFolderModal');
            browseRemoteDirectory(state.activeTabPeer, remotePath);
        } else {
            showToast(data.error || 'Create folder failed', 'error');
        }
    } catch (e) {
        showToast('Network error', 'error');
    }
    hideLoading();
}

// ── Tab init (called from initBridge) ─────────────────────────────────────

function initPeerTabs() {
    const localTab = document.getElementById('tab-local');
    if (localTab) {
        localTab.addEventListener('click', () => {
            if (!state.activeTabPeer) return; // already on local
            switchToLocalTab();
        });
    }
}

// =============================================================
// Server Bridge
// =============================================================

// Bridge state: peers we are connected to, and their transfer tasks.
const bridgeState = {
    peers: [],          // [{id, name, url, connected_at}]
    transfers: {},      // task_id -> transfer object (for transfer center)
    remotePath: '',     // currently browsed remote path in receive modal
    remotePeerId: '',   // peer being browsed in receive modal
    selectedRemoteFiles: [], // [{path, name}] selected in receive modal
};

// ── Initialisation ────────────────────────────────────────────────────────

function initBridge() {
    initPeerTabs();

    // Wire up sidebar buttons.
    const genBtn = document.getElementById('bridgeGenerateBtn');
    if (genBtn) genBtn.addEventListener('click', openBridgeGenerateModal);

    const connBtn = document.getElementById('bridgeConnectBtn');
    if (connBtn) connBtn.addEventListener('click', openBridgeConnectModal);

    // Wire up modal buttons.
    const doGenBtn = document.getElementById('bridgeDoGenerateBtn');
    if (doGenBtn) doGenBtn.addEventListener('click', doBridgeGenerate);

    const copyBtn = document.getElementById('bridgeCopyCodeBtn');
    if (copyBtn) copyBtn.addEventListener('click', copyBridgeCode);

    const doConnBtn = document.getElementById('bridgeDoConnectBtn');
    if (doConnBtn) doConnBtn.addEventListener('click', doBridgeConnect);

    const doSendBtn = document.getElementById('bridgeDoSendBtn');
    if (doSendBtn) doSendBtn.addEventListener('click', doBridgeSend);

    const browseBtn = document.getElementById('bridgeBrowseBtn');
    if (browseBtn) browseBtn.addEventListener('click', doBridgeBrowse);

    const doReceiveBtn = document.getElementById('bridgeDoReceiveBtn');
    if (doReceiveBtn) doReceiveBtn.addEventListener('click', doBridgeReceive);

    // Refresh peer list every 10 s and poll bridge transfers every 2 s.
    refreshBridgePeers();
    setInterval(refreshBridgePeers, 10000);
    setInterval(refreshBridgeTransfers, 2000);
}

// ── Peer list ─────────────────────────────────────────────────────────────

async function refreshBridgePeers() {
    try {
        const resp = await fetch('/api/bridge/peers');
        if (!resp.ok) return;
        const prevIds = new Set(bridgeState.peers.map(p => p.id));
        bridgeState.peers = await resp.json();

        // Add tabs for newly-connected peers; remove tabs for gone peers.
        const currentIds = new Set(bridgeState.peers.map(p => p.id));
        bridgeState.peers.forEach(p => { if (!prevIds.has(p.id)) addPeerTab(p); });
        prevIds.forEach(id => { if (!currentIds.has(id)) removePeerTab(id); });

        renderBridgePeerList();
        updatePeerBadge();
    } catch (e) { /* ignore */ }
}

function renderBridgePeerList() {
    const container = document.getElementById('bridgePeerList');
    if (!container) return;

    if (!bridgeState.peers.length) {
        container.innerHTML = '<p class="sidebar-empty">No peers connected</p>';
        return;
    }

    container.innerHTML = bridgeState.peers.map(p => `
        <div class="bridge-peer-item" data-peer-id="${escapeHtml(p.id)}">
            <span class="bridge-peer-icon"><i class="fas fa-server"></i></span>
            <span class="bridge-peer-name" title="${escapeHtml(p.url)}">${escapeHtml(p.name)}</span>
            <button class="btn btn-icon btn-tiny bridge-browse-btn" title="Open tab to browse this server" data-peer-id="${escapeHtml(p.id)}">
                <i class="fas fa-external-link-alt"></i>
            </button>
            <button class="btn btn-icon btn-tiny bridge-receive-btn" title="Receive files from this server" data-peer-id="${escapeHtml(p.id)}">
                <i class="fas fa-download"></i>
            </button>
            <button class="btn btn-icon btn-tiny bridge-disconnect-btn" title="Disconnect" data-peer-id="${escapeHtml(p.id)}">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');

    container.querySelectorAll('.bridge-browse-btn').forEach(btn => {
        btn.addEventListener('click', () => switchToPeerTab(btn.dataset.peerId));
    });
    container.querySelectorAll('.bridge-disconnect-btn').forEach(btn => {
        btn.addEventListener('click', () => disconnectBridgePeer(btn.dataset.peerId));
    });
    container.querySelectorAll('.bridge-receive-btn').forEach(btn => {
        btn.addEventListener('click', () => openBridgeReceiveModal(btn.dataset.peerId));
    });
}

async function disconnectBridgePeer(peerId) {
    try {
        const resp = await fetch(`/api/bridge/disconnect/${encodeURIComponent(peerId)}`, { method: 'DELETE' });
        if (resp.ok) {
            showToast('Peer disconnected', 'info');
            removePeerTab(peerId);
            refreshBridgePeers();
        } else {
            const d = await resp.json();
            showToast(d.error || 'Disconnect failed', 'error');
        }
    } catch (e) {
        showToast('Network error', 'error');
    }
}

// ── Generate pairing code ─────────────────────────────────────────────────

function openBridgeGenerateModal() {
    document.getElementById('bridgeCodeResult').style.display = 'none';
    document.getElementById('bridgeCodeText').value = '';
    // Pre-fill with the server's tunnel URL if available
    const tunnelUrl = elements.tunnelUrl ? elements.tunnelUrl.textContent : '';
    document.getElementById('bridgeMyUrl').value =
        tunnelUrl || (window.location.protocol + '//' + window.location.host);
    openModal('bridgeGenerateModal');
}

async function doBridgeGenerate() {
    const url = document.getElementById('bridgeMyUrl').value.trim();
    if (!url) {
        showToast('Please enter your server URL', 'warning');
        return;
    }
    try {
        const resp = await fetch(
            '/api/bridge/generate-code?' + new URLSearchParams({ url })
        );
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Failed to generate code', 'error');
            return;
        }
        document.getElementById('bridgeCodeText').value = data.code;
        document.getElementById('bridgeCodeResult').style.display = '';
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}

function copyBridgeCode() {
    const txt = document.getElementById('bridgeCodeText').value;
    if (!txt) return;
    navigator.clipboard.writeText(txt).then(() => {
        showToast('Pairing code copied to clipboard', 'success');
    }).catch(() => {
        // Fallback for environments without clipboard API (may not work in all browsers)
        try {
            document.getElementById('bridgeCodeText').select();
            const ok = document.execCommand('copy');
            showToast(ok ? 'Pairing code copied' : 'Copy manually from the text box', ok ? 'success' : 'info');
        } catch (e) {
            showToast('Please copy the code manually from the text box', 'info');
        }
    });
}

// ── Connect to peer ───────────────────────────────────────────────────────

function openBridgeConnectModal() {
    document.getElementById('bridgePasteCode').value = '';
    document.getElementById('bridgeMyName').value = '';
    openModal('bridgeConnectModal');
}

async function doBridgeConnect() {
    const code = document.getElementById('bridgePasteCode').value.trim();
    const name = document.getElementById('bridgeMyName').value.trim() || 'Server';
    if (!code) {
        showToast('Please paste the pairing code', 'warning');
        return;
    }
    showLoading();
    try {
        const resp = await fetch('/api/bridge/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, name }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Connection failed', 'error');
            return;
        }
        const peerName = data.peer_name || 'peer';
        showToast('Connected to "' + peerName + '"', 'success');

        // Update status bar immediately.
        elements.statusText.textContent = `Connected to: ${peerName}`;
        setTimeout(() => {
            if (elements.statusText.textContent.startsWith('Connected to:')) {
                elements.statusText.textContent = 'Ready';
            }
        }, 5000);

        closeModal('bridgeConnectModal');
        // Refresh peer list; the peer list handler will add the tab automatically.
        await refreshBridgePeers();

        // Auto-switch to the new peer's tab if one was created.
        const newPeer = bridgeState.peers.find(p => p.name === peerName || p.id === data.peer_id);
        if (newPeer) switchToPeerTab(newPeer.id);
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
    hideLoading();
}

// ── Send files to peer (push) ─────────────────────────────────────────────

function openBridgeSendModal(filePaths) {
    if (!bridgeState.peers.length) {
        showToast('No peers connected. Connect a peer first.', 'warning');
        return;
    }

    // Render file list
    const listEl = document.getElementById('bridgeSendFilesList');
    listEl.innerHTML = filePaths.map(p => `
        <div class="item"><i class="fas fa-file"></i> ${escapeHtml(p)}</div>
    `).join('');

    // Populate peer selector
    const sel = document.getElementById('bridgeSendPeer');
    sel.innerHTML = bridgeState.peers.map(p =>
        `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.url)})</option>`
    ).join('');

    // Default destination
    document.getElementById('bridgeSendDest').value = '';

    // Store files for submit handler
    sel.dataset.files = JSON.stringify(filePaths);

    openModal('bridgeSendModal');
}

async function doBridgeSend() {
    const peerId = document.getElementById('bridgeSendPeer').value;
    const dest   = document.getElementById('bridgeSendDest').value.trim();
    const files  = JSON.parse(document.getElementById('bridgeSendPeer').dataset.files || '[]');

    if (!peerId) { showToast('Select a peer server', 'warning'); return; }
    if (!dest)   { showToast('Enter the remote destination path', 'warning'); return; }
    if (!files.length) { showToast('No files selected', 'warning'); return; }

    showLoading();
    try {
        const resp = await fetch('/api/bridge/push', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ peer_id: peerId, files, destination: dest }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Push failed', 'error');
            return;
        }
        closeModal('bridgeSendModal');
        showToast(data.message || 'Transfer started', 'success');
        showTransferCenter();
        // Register a local transfer entry so it appears in the Transfer Center.
        const taskId = data.task_id;
        const peer = bridgeState.peers.find(p => p.id === peerId) || {};
        bridgeState.transfers['bt-' + taskId] = makeBridgeTransfer('bt-' + taskId, {
            id: taskId,
            kind: 'bridge-push',
            peer_name: peer.name || 'Peer',
            current_file: '',
            status: 'pending',
            progress: 0,
            transferred: 0,
            total_size: 0,
            speed: 0,
        });
        renderTransfers();
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
    hideLoading();
}

// ── Receive files from peer (pull) ────────────────────────────────────────

function openBridgeReceiveModal(preselectedPeerId) {
    if (!bridgeState.peers.length) {
        showToast('No peers connected. Connect a peer first.', 'warning');
        return;
    }

    const sel = document.getElementById('bridgeReceivePeer');
    sel.innerHTML = bridgeState.peers.map(p =>
        `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.url)})</option>`
    ).join('');

    if (preselectedPeerId) sel.value = preselectedPeerId;

    bridgeState.selectedRemoteFiles = [];
    bridgeState.remotePath = '';
    bridgeState.remotePeerId = sel.value;
    document.getElementById('bridgeRemotePath').textContent = '';
    document.getElementById('bridgeRemoteList').innerHTML =
        '<p style="padding:8px;opacity:.6;">Click Browse to explore the remote server</p>';
    document.getElementById('bridgeReceiveFilesList').innerHTML = '';
    document.getElementById('bridgeReceiveDest').value = state.currentPath || serverHome || '';

    openModal('bridgeReceiveModal');
}

async function doBridgeBrowse() {
    const peerId = document.getElementById('bridgeReceivePeer').value;
    if (!peerId) { showToast('Select a peer server', 'warning'); return; }

    bridgeState.remotePeerId = peerId;
    await bridgeBrowsePath(peerId, bridgeState.remotePath || '');
}

async function bridgeBrowsePath(peerId, path) {
    try {
        const params = new URLSearchParams({ peer_id: peerId });
        if (path) params.set('path', path);
        const resp = await fetch('/api/bridge/peer-browse?' + params);
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Browse failed', 'error');
            return;
        }
        bridgeState.remotePath = data.current_path || path;
        renderBridgeRemoteList(data);
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}

function renderBridgeRemoteList(data) {
    const pathEl = document.getElementById('bridgeRemotePath');
    const listEl = document.getElementById('bridgeRemoteList');
    if (!pathEl || !listEl) return;

    pathEl.textContent = data.current_path || '';

    let html = '';
    if (data.parent_path && data.parent_path !== data.current_path) {
        html += `<div class="folder-item bridge-remote-nav" data-path="${escapeHtml(data.parent_path)}" data-is-dir="true">
            <i class="fas fa-arrow-left"></i> ..
        </div>`;
    }

    (data.items || []).forEach(item => {
        const icon = item.is_dir ? 'fa-folder' : 'fa-file';
        html += `<div class="folder-item" data-path="${escapeHtml(item.path)}" data-is-dir="${item.is_dir}" data-name="${escapeHtml(item.name)}">
            <i class="fas ${icon}"></i>
            <span>${escapeHtml(item.name)}</span>
            ${item.is_dir ? '' : `<button class="btn btn-icon btn-tiny bridge-select-file-btn" data-path="${escapeHtml(item.path)}" data-name="${escapeHtml(item.name)}" title="Select this file"><i class="fas fa-plus"></i></button>`}
        </div>`;
    });

    if (!html) html = '<p style="padding:8px;opacity:.6;">Empty folder</p>';
    listEl.innerHTML = html;

    listEl.querySelectorAll('.bridge-remote-nav').forEach(el => {
        el.addEventListener('click', () => {
            bridgeBrowsePath(bridgeState.remotePeerId, el.dataset.path);
        });
    });
    listEl.querySelectorAll('.folder-item[data-is-dir="true"]:not(.bridge-remote-nav)').forEach(el => {
        el.addEventListener('dblclick', () => {
            bridgeBrowsePath(bridgeState.remotePeerId, el.dataset.path);
        });
    });
    listEl.querySelectorAll('.bridge-select-file-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            addBridgeSelectedFile(btn.dataset.path, btn.dataset.name);
        });
    });
}

function addBridgeSelectedFile(path, name) {
    if (bridgeState.selectedRemoteFiles.some(f => f.path === path)) {
        showToast('File already selected', 'info');
        return;
    }
    bridgeState.selectedRemoteFiles.push({ path, name });
    renderBridgeSelectedFiles();
}

function renderBridgeSelectedFiles() {
    const el = document.getElementById('bridgeReceiveFilesList');
    if (!el) return;
    if (!bridgeState.selectedRemoteFiles.length) {
        el.innerHTML = '';
        return;
    }
    el.innerHTML = bridgeState.selectedRemoteFiles.map((f, i) => `
        <div class="item" style="display:flex;align-items:center;gap:6px;">
            <i class="fas fa-file"></i>
            <span style="flex:1">${escapeHtml(f.name)}</span>
            <button class="btn btn-icon btn-tiny" data-index="${i}" title="Remove">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');
    el.querySelectorAll('button[data-index]').forEach(btn => {
        btn.addEventListener('click', () => {
            bridgeState.selectedRemoteFiles.splice(Number(btn.dataset.index), 1);
            renderBridgeSelectedFiles();
        });
    });
}

async function doBridgeReceive() {
    const peerId = document.getElementById('bridgeReceivePeer').value;
    const dest   = document.getElementById('bridgeReceiveDest').value.trim();
    const files  = bridgeState.selectedRemoteFiles.map(f => f.path);

    if (!peerId) { showToast('Select a peer server', 'warning'); return; }
    if (!dest)   { showToast('Enter the local destination path', 'warning'); return; }
    if (!files.length) { showToast('Select at least one remote file', 'warning'); return; }

    showLoading();
    try {
        const resp = await fetch('/api/bridge/pull', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ peer_id: peerId, files, destination: dest }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Pull failed', 'error');
            return;
        }
        closeModal('bridgeReceiveModal');
        showToast(data.message || 'Transfer started', 'success');
        showTransferCenter();

        const taskId = data.task_id;
        const peer = bridgeState.peers.find(p => p.id === peerId) || {};
        bridgeState.transfers['bt-' + taskId] = makeBridgeTransfer('bt-' + taskId, {
            id: taskId,
            kind: 'bridge-pull',
            peer_name: peer.name || 'Peer',
            current_file: '',
            status: 'pending',
            progress: 0,
            transferred: 0,
            total_size: 0,
            speed: 0,
        });
        renderTransfers();
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
    hideLoading();
}

// ── Transfer Center integration ───────────────────────────────────────────

function makeBridgeTransfer(id, task) {
    const taskId = task.id;
    const transfer = {
        id,
        kind: task.kind,       // 'bridge-push' | 'bridge-pull'
        filename: task.current_file || task.peer_name || 'bridge transfer',
        status: task.status,
        transferred: task.transferred || 0,
        total: task.total_size || 0,
        speed: task.speed || 0,
        error: task.error || null,
        startedAt: (task.created_at || Date.now() / 1000) * 1000,
        _serverTaskId: taskId,
        _peerName: task.peer_name || '',
        _currentFile: task.current_file || '',
    };
    transfer.cancel = async () => {
        try {
            await fetch(`/api/bridge/cancel-transfer/${taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
        refreshBridgeTransfers();
    };
    transfer.dismiss = async () => {
        try {
            await fetch(`/api/bridge/dismiss-transfer/${taskId}`, { method: 'POST' });
        } catch (e) { /* ignore */ }
    };
    return transfer;
}

async function refreshBridgeTransfers() {
    let tasks;
    try {
        const resp = await fetch('/api/bridge/transfers');
        if (!resp.ok) return;
        tasks = await resp.json();
    } catch (e) { return; }
    if (!Array.isArray(tasks)) return;

    const seenIds = new Set();
    tasks.forEach(task => {
        const id = 'bt-' + task.id;
        seenIds.add(id);
        let transfer = state.transfers[id];
        if (!transfer) {
            transfer = makeBridgeTransfer(id, task);
            state.transfers[id] = transfer;
        }
        let status = task.status;
        if (status === 'pending' || status === 'running') status = 'downloading';
        transfer.status = status;
        transfer.transferred = task.transferred || 0;
        transfer.total = task.total_size || 0;
        transfer.speed = task.speed || 0;
        transfer.error = task.error || null;
        transfer._peerName = task.peer_name || transfer._peerName;
        transfer._currentFile = task.current_file || '';
        transfer.filename = task.current_file || task.peer_name || transfer.filename;
    });

    // Clean up dismissed/gone tasks from the transfer center.
    Object.keys(state.transfers).forEach(id => {
        if (id.startsWith('bt-') && !seenIds.has(id)) {
            delete state.transfers[id];
        }
    });

    renderTransfers();
}

// "Send to Server" handler called from context menu action 'bridge-send'.
function handleBridgeSend() {
    if (!state.selectedItem) return;
    if (!bridgeState.peers.length) {
        showToast('No peers connected. Use "Server Bridge" in the sidebar to connect first.', 'warning');
        return;
    }
    openBridgeSendModal([state.selectedItem.path]);
}

// ── Hook into app init ────────────────────────────────────────────────────

// Extend the existing init() setup to include bridge initialisation.
document.addEventListener('DOMContentLoaded', () => {
    initBridge();
});

