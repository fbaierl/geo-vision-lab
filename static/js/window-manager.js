/**
 * Window Manager - handles window focus, drag, resize, minimize, maximize, and snap layout
 */

export class WindowManager {
    constructor() {
        this.windows = new Map();
        this.zIndexCounter = 1000;
        this.activeWindow = null;
        this.dragState = null;
        this.resizeState = null;
        this.snapped = false;
        this.preSnapState = null;

        this.init();
    }

    init() {
        // Initialize all windows
        document.querySelectorAll('.window').forEach(win => {
            this.registerWindow(win);
        });

        // Set up shelf toggles
        document.querySelectorAll('.shelf-item').forEach(item => {
            item.addEventListener('click', () => {
                const targetId = item.getAttribute('data-target');
                this.toggleWindow(targetId);
            });
        });

        // Snap layout button
        const snapBtn = document.getElementById('snap-layout-btn');
        if (snapBtn) {
            snapBtn.addEventListener('click', () => this.toggleSnapLayout());
        }

        // Global mouse events for drag/resize
        document.addEventListener('mousemove', (e) => this.handleMouseMove(e));
        document.addEventListener('mouseup', (e) => this.handleMouseUp(e));

        // Apply snap layout on init
        this.applySnapLayout();
        if (snapBtn) snapBtn.classList.add('active');
        this.snapped = true;

        // Focus first window
        this.focusWindow('window-chat');
    }

    registerWindow(win) {
        const id = win.id;
        const header = win.querySelector('.window-header');

        this.windows.set(id, {
            element: win,
            minimized: false,
            maximized: false,
            rect: null
        });

        // Header click for dragging
        header.addEventListener('mousedown', (e) => this.handleHeaderMouseDown(e, win));

        // Window click for focus
        win.addEventListener('mousedown', () => this.focusWindow(id));

        // Window controls
        win.querySelector('.window-btn.minimize').addEventListener('click', (e) => {
            e.stopPropagation();
            this.minimizeWindow(id);
        });

        win.querySelector('.window-btn.maximize').addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleMaximize(id);
            e.preventDefault();
        });

        win.querySelector('.window-btn.close').addEventListener('click', (e) => {
            e.stopPropagation();
            this.minimizeWindow(id);
        });

        // Resize handles
        const resizeHandles = win.querySelectorAll('.window-resize-handle');
        resizeHandles.forEach(handle => {
            handle.addEventListener('mousedown', (e) => this.handleResizeMouseDown(e, win, handle.className));
        });
    }

    focusWindow(id) {
        const winData = this.windows.get(id);
        if (!winData) return;

        // Update z-index
        this.zIndexCounter++;
        winData.element.style.zIndex = this.zIndexCounter;

        // Update focused state
        document.querySelectorAll('.window.focused').forEach(w => w.classList.remove('focused'));
        winData.element.classList.add('focused');
        this.activeWindow = id;

        // Update shelf
        document.querySelectorAll('.shelf-item').forEach(item => {
            item.classList.toggle('active', item.getAttribute('data-target') === id);
        });
    }

    toggleWindow(id) {
        const winData = this.windows.get(id);
        if (!winData) return;

        if (winData.minimized) {
            this.restoreWindow(id);
        } else {
            if (winData.element.classList.contains('focused')) {
                this.minimizeWindow(id);
            } else {
                this.focusWindow(id);
            }
        }
    }

    minimizeWindow(id) {
        const winData = this.windows.get(id);
        if (!winData) return;

        winData.minimized = true;
        winData.element.classList.add('minimized');

        // Update shelf indicator
        const shelfItem = document.querySelector(`.shelf-item[data-target="${id}"]`);
        if (shelfItem) {
            shelfItem.classList.add('minimized');
            shelfItem.classList.remove('active');
        }
    }

    restoreWindow(id) {
        const winData = this.windows.get(id);
        if (!winData) return;

        winData.minimized = false;
        winData.element.classList.remove('minimized');
        this.focusWindow(id);

        // Update shelf indicator
        const shelfItem = document.querySelector(`.shelf-item[data-target="${id}"]`);
        if (shelfItem) {
            shelfItem.classList.remove('minimized');
        }
    }

    toggleMaximize(id) {
        const winData = this.windows.get(id);
        if (!winData) return;

        if (winData.maximized) {
            // Restore from maximized
            winData.maximized = false;
            winData.element.classList.remove('maximized');
            // Restore position if we have it stored
            if (winData.restoreRect) {
                winData.element.style.width = winData.restoreRect.width + 'px';
                winData.element.style.height = winData.restoreRect.height + 'px';
                winData.element.style.left = winData.restoreRect.left + 'px';
                winData.element.style.top = winData.restoreRect.top + 'px';
                winData.element.style.transform = 'none';
            }
        } else {
            // Store current rect for restoration
            const rect = winData.element.getBoundingClientRect();
            winData.restoreRect = {
                width: rect.width,
                height: rect.height,
                left: rect.left,
                top: rect.top
            };
            winData.maximized = true;
            winData.element.classList.add('maximized');
        }

        this.focusWindow(id);
    }

    handleHeaderMouseDown(e, win) {
        if (e.target.classList.contains('window-btn')) return;

        const id = win.id;
        const winData = this.windows.get(id);
        if (winData.maximized) return;

        this.focusWindow(id);

        const rect = win.getBoundingClientRect();
        this.dragState = {
            windowId: id,
            offsetX: e.clientX - rect.left,
            offsetY: e.clientY - rect.top
        };

        e.preventDefault();
    }

    handleResizeMouseDown(e, win, handleClass) {
        e.stopPropagation();
        e.preventDefault();

        const id = win.id;
        const winData = this.windows.get(id);
        if (winData.maximized) return;

        this.focusWindow(id);

        const rect = win.getBoundingClientRect();
        this.resizeState = {
            windowId: id,
            startX: e.clientX,
            startY: e.clientY,
            startWidth: rect.width,
            startHeight: rect.height,
            startLeft: rect.left,
            startTop: rect.top,
            isRight: handleClass.includes('right'),
            isBottom: handleClass.includes('bottom'),
            isCorner: handleClass.includes('corner')
        };
    }

    handleMouseMove(e) {
        if (this.dragState) {
            const { windowId, offsetX, offsetY } = this.dragState;
            const win = document.getElementById(windowId);
            const desktop = document.getElementById('desktop');
            const desktopRect = desktop.getBoundingClientRect();

            const relativeX = e.clientX - desktopRect.left - offsetX;
            const relativeY = e.clientY - desktopRect.top - offsetY;

            const maxX = desktopRect.width - win.offsetWidth;
            const maxY = desktopRect.height - win.offsetHeight;

            const constrainedX = Math.max(0, Math.min(relativeX, maxX));
            const constrainedY = Math.max(0, Math.min(relativeY, maxY));

            win.style.left = constrainedX + 'px';
            win.style.top = constrainedY + 'px';
            win.style.transform = 'none';
        }

        if (this.resizeState) {
            const { windowId, startX, startY, startWidth, startHeight, startLeft, startTop, isRight, isBottom, isCorner } = this.resizeState;
            const win = document.getElementById(windowId);

            let newWidth = startWidth;
            let newHeight = startHeight;
            let newLeft = startLeft;
            let newTop = startTop;

            if (isRight || isCorner) {
                newWidth = Math.max(300, startWidth + (e.clientX - startX));
            }
            if (isBottom || isCorner) {
                newHeight = Math.max(200, startHeight + (e.clientY - startY));
            }

            win.style.width = newWidth + 'px';
            win.style.height = newHeight + 'px';
            win.style.left = newLeft + 'px';
            win.style.top = newTop + 'px';
        }
    }

    handleMouseUp(e) {
        this.dragState = null;
        this.resizeState = null;
    }

    toggleSnapLayout() {
        const snapBtn = document.getElementById('snap-layout-btn');

        if (this.snapped) {
            this.restoreFromSnap();
            if (snapBtn) snapBtn.classList.remove('active');
        } else {
            this.applySnapLayout();
            if (snapBtn) snapBtn.classList.add('active');
        }

        this.snapped = !this.snapped;
    }

    applySnapLayout() {
        const desktop = document.getElementById('desktop');
        const desktopRect = desktop.getBoundingClientRect();
        const padding = 10;

        const visibleWindows = [];
        this.windows.forEach((winData, id) => {
            if (!winData.minimized) {
                visibleWindows.push({ id, ...winData });
            }
        });

        if (visibleWindows.length === 0) return;

        this.preSnapState = visibleWindows.map(win => ({
            id: win.id,
            rect: {
                width: win.element.offsetWidth,
                height: win.element.offsetHeight,
                left: parseFloat(win.element.style.left) || 0,
                top: parseFloat(win.element.style.top) || 0
            }
        }));

        const availableWidth = desktopRect.width - (padding * 2);
        const availableHeight = desktopRect.height - (padding * 2);

        const windowConfigs = {
            'window-chat': { widthRatio: 0.35, heightRatio: 0.85, name: 'chat' },
            'window-reasoning': { widthRatio: 0.25, heightRatio: 0.85, name: 'reasoning' },
            'window-history': { widthRatio: 0.20, heightRatio: 0.35, name: 'history' },
            'window-services': { widthRatio: 0.20, heightRatio: 0.35, name: 'services' },
            'window-maps': { widthRatio: 0.55, heightRatio: 0.45, name: 'maps' },
            'window-graph': { widthRatio: 0.55, heightRatio: 0.45, name: 'graph' }
        };

        const numWindows = visibleWindows.length;

        if (numWindows === 1) {
            const win = visibleWindows[0];
            win.element.style.width = Math.min(800, availableWidth) + 'px';
            win.element.style.height = Math.min(600, availableHeight) + 'px';
            win.element.style.left = padding + 'px';
            win.element.style.top = padding + 'px';
            win.element.style.transform = 'none';
        } else if (numWindows === 2) {
            const halfWidth = (availableWidth / 2) - (padding / 2);
            visibleWindows.forEach((win, idx) => {
                win.element.style.width = halfWidth + 'px';
                win.element.style.height = (availableHeight * 0.7) + 'px';
                win.element.style.left = padding + (idx * (halfWidth + padding)) + 'px';
                win.element.style.top = padding + 'px';
                win.element.style.transform = 'none';
            });
        } else if (numWindows === 3) {
            const halfWidth = (availableWidth / 2) - (padding / 2);
            visibleWindows.forEach((win, idx) => {
                if (idx < 2) {
                    win.element.style.width = halfWidth + 'px';
                    win.element.style.height = (availableHeight * 0.55) + 'px';
                    win.element.style.left = padding + (idx * (halfWidth + padding)) + 'px';
                    win.element.style.top = padding + 'px';
                } else {
                    win.element.style.width = availableWidth + 'px';
                    win.element.style.height = (availableHeight * 0.35) + 'px';
                    win.element.style.left = padding + 'px';
                    win.element.style.top = padding + (availableHeight * 0.55) + (padding * 2) + 'px';
                }
                win.element.style.transform = 'none';
            });
        } else {
            const leftColWidth = availableWidth * 0.25;
            const midColWidth = availableWidth * 0.20;
            const rightColWidth = availableWidth * 0.50;
            const smallHeight = availableHeight * 0.30;
            const tallHeight = availableHeight * 0.65;
            const mapsHeight = availableHeight * 0.25;
            const graphHeight = availableHeight * 0.70;

            const priorityOrder = ['window-chat', 'window-reasoning', 'window-maps', 'window-graph', 'window-history', 'window-services'];
            visibleWindows.sort((a, b) => {
                const aIdx = priorityOrder.indexOf(a.id);
                const bIdx = priorityOrder.indexOf(b.id);
                return (aIdx === -1 ? 999 : aIdx) - (bIdx === -1 ? 999 : bIdx);
            });

            let leftY = padding;
            let midY = padding;
            let rightY = padding;

            visibleWindows.forEach((win) => {
                const config = windowConfigs[win.id];
                if (!config) {
                    win.element.style.width = (availableWidth / 3) + 'px';
                    win.element.style.height = (availableHeight / 2) + 'px';
                    return;
                }

                if (win.id === 'window-chat') {
                    win.element.style.width = leftColWidth + 'px';
                    win.element.style.height = tallHeight + 'px';
                    win.element.style.left = padding + 'px';
                    win.element.style.top = padding + 'px';
                    leftY = padding + tallHeight + padding;
                } else if (win.id === 'window-history') {
                    win.element.style.width = leftColWidth + 'px';
                    win.element.style.height = smallHeight + 'px';
                    win.element.style.left = padding + 'px';
                    win.element.style.top = leftY + 'px';
                } else if (win.id === 'window-reasoning') {
                    win.element.style.width = midColWidth + 'px';
                    win.element.style.height = tallHeight + 'px';
                    win.element.style.left = padding + leftColWidth + padding + 'px';
                    win.element.style.top = padding + 'px';
                    midY = padding + tallHeight + padding;
                } else if (win.id === 'window-services') {
                    win.element.style.width = midColWidth + 'px';
                    win.element.style.height = smallHeight + 'px';
                    win.element.style.left = padding + leftColWidth + padding + 'px';
                    win.element.style.top = midY + 'px';
                } else if (win.id === 'window-maps') {
                    win.element.style.width = rightColWidth + 'px';
                    win.element.style.height = mapsHeight + 'px';
                    win.element.style.left = padding + leftColWidth + padding + midColWidth + padding + 'px';
                    win.element.style.top = padding + 'px';
                    rightY = padding + mapsHeight + padding;
                } else if (win.id === 'window-graph') {
                    win.element.style.width = rightColWidth + 'px';
                    win.element.style.height = graphHeight + 'px';
                    win.element.style.left = padding + leftColWidth + padding + midColWidth + padding + 'px';
                    win.element.style.top = rightY + 'px';
                }
                win.element.style.transform = 'none';
            });
        }

        this.focusWindow('window-chat');
    }

    restoreFromSnap() {
        if (!this.preSnapState) return;

        this.preSnapState.forEach(winState => {
            const winData = this.windows.get(winState.id);
            if (winData) {
                winData.element.style.width = winState.rect.width + 'px';
                winData.element.style.height = winState.rect.height + 'px';
                winData.element.style.left = winState.rect.left + 'px';
                winData.element.style.top = winState.rect.top + 'px';
                winData.element.style.transform = 'none';
            }
        });

        this.preSnapState = null;
    }
}
