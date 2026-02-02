document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const itemList = document.getElementById('item-list');
    const listContainer = document.getElementById('list-container');
    const controlPanel = document.getElementById('control-panel');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');

    let items = []; // Stores current list of items
    let isProcessing = false;
    let abortController = null;

    // --- Drag & Drop ---
    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });

    async function handleFiles(files) {
        if (files.length === 0) return;

        const file = files[0];
        const formData = new FormData();
        formData.append('file', file);

        try {
            dropZone.innerHTML = '<i class="fas fa-spinner fa-spin"></i><h3>Parsing...</h3>';

            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                items = data.items;
                renderList();
                showControls(true);
                dropZone.innerHTML = `<i class="fas fa-check-circle" style="color: var(--success)"></i><h3>${file.name} Loaded</h3><p>${items.length} items found</p>`;
            } else {
                alert('Error: ' + data.error);
                dropZone.innerHTML = '<i class="fas fa-cloud-upload-alt"></i><h3>Drag & Drop CSV/Excel here</h3><p>or click to browse</p>';
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Upload failed');
            dropZone.innerHTML = '<i class="fas fa-cloud-upload-alt"></i><h3>Drag & Drop CSV/Excel here</h3><p>or click to browse</p>';
        }
    }

    function renderList() {
        itemList.innerHTML = '';
        items.forEach((item, index) => {
            const li = document.createElement('li');
            li.className = 'list-item';
            li.id = `item-${index}`;

            li.innerHTML = `
                <div class="item-info">
                    <h4>${item.Name}</h4>
                    <span>${item.SKU}</span>
                </div>
                <div class="item-actions">
                    <span class="status-badge pending" data-sku="${item.SKU}" id="status-${item.SKU}">Pending</span>
                    <button class="delete-btn" onclick="deleteItem('${item.SKU}')"><i class="fas fa-trash"></i></button>
                </div>
            `;
            itemList.appendChild(li);
        });
        listContainer.classList.remove('hidden');
        updateProgress(0);
    }

    window.deleteItem = (sku) => {
        if (isProcessing) return;

        const index = items.findIndex(i => i.SKU === sku);
        if (index > -1) {
            // Find element by data attribute in badge
            const badges = document.querySelectorAll('.status-badge');
            let targetLi = null;
            badges.forEach(b => {
                if (b.dataset.sku === sku) {
                    targetLi = b.closest('.list-item');
                }
            });

            if (targetLi) {
                targetLi.classList.add('fading-out');
                targetLi.addEventListener('animationend', () => {
                    targetLi.remove();
                    items.splice(index, 1);
                    updateProgress(0);
                });
            }
        }
    };

    function showControls(show) {
        if (show) controlPanel.classList.remove('hidden');
        else controlPanel.classList.add('hidden');
    }

    function updateProgress(processedCount) {
        const total = items.length;
        const percent = total === 0 ? 0 : (processedCount / total) * 100;
        progressBar.style.width = `${percent}%`;
        progressText.textContent = `${processedCount} / ${total}`;
    }

    // Stop Button Logic
    stopBtn.addEventListener('click', () => {
        if (abortController) {
            abortController.abort();
            abortController = null;
            isProcessing = false;
            resetControlsState();
            // Don't alert, just log or small toast if we had one. 
            // Alert is annoying. 
            console.log('Stopped by user');
        }
    });

    function resetControlsState() {
        startBtn.disabled = false;
        startBtn.innerHTML = 'Start Sourcing <i class="fas fa-play"></i>';
        startBtn.classList.remove('hidden');

        stopBtn.classList.add('hidden');

        document.querySelectorAll('.delete-btn').forEach(b => b.disabled = false);
    }

    startBtn.addEventListener('click', async () => {
        if (isProcessing) return;
        isProcessing = true;
        abortController = new AbortController();
        const signal = abortController.signal;

        startBtn.disabled = true;
        startBtn.classList.add('hidden');

        stopBtn.classList.remove('hidden');
        stopBtn.disabled = false;

        document.querySelectorAll('.delete-btn').forEach(b => b.disabled = true);

        let processedCount = 0;
        const outputDir = document.getElementById('output-dir').value;
        const uploadToWordpress = document.getElementById('wp-toggle').checked;

        try {
            const response = await fetch('/api/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    items: items,
                    output_dir: outputDir,
                    upload_to_wordpress: uploadToWordpress
                }),
                signal: signal
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

    
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            updateItemStatus(data);
                            if (data.Status === 'Success' || data.Status === 'Failed' || data.Status === 'Skipped' || data.Status === 'Assigned' || data.Status === 'Skipped (Duplicate)' || data.Status === 'Uploaded' || data.Status === 'No Image Found') {
                                processedCount++;
                                updateProgress(processedCount); 
                            }
                        } catch (e) {
                            console.error('Error parsing SSE:', e);
                        }
                    }
                }
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('Fetch aborted');
            } else {
                console.error('Stream Error:', error);
                alert('Processing error occurred');
            }
        } finally {
            if (isProcessing) {
                isProcessing = false;
                resetControlsState();
            }
        }
    });

    function updateItemStatus(data) {
        const badge = document.getElementById(`status-${data.SKU}`);

        if (badge) {
            badge.textContent = data.Status;
            badge.className = 'status-badge';

            if (data.Status === 'Success' || data.Status === 'Assigned') {
                badge.classList.add('success');
                badge.innerHTML = data.Status;
            }
            else if (data.Status === 'Failed') {
                badge.classList.add('failed');
                badge.innerHTML = 'Failed';
            }
            else if (data.Status === 'Skipped' || data.Status === 'Skipped (Duplicate)') {
                badge.classList.add('skipped');
                badge.innerHTML = data.Status;
            }
            else if (data.Status === 'Downloading' || data.Status === 'Searching' || data.Status === 'Checking WordPress') {
                badge.classList.add('in-progress');
                badge.innerHTML = `<span class="spinner"></span> ${data.Status}`;
            }
            else if (data.Status === 'Uploading to WordPress' || data.Status === 'Assigning Image') {
                badge.classList.add('uploading');
                badge.innerHTML = `<span class="spinner"></span> ${data.Status}`;
            }
            else if (data.Status === 'Uploaded') {
                badge.classList.add('success');
                badge.innerHTML = '<i class="fab fa-wordpress"></i> Uploaded';
            }
            else if (data.Status === 'No Image Found') {
                badge.classList.add('failed');
                badge.innerHTML = `<i class="fas fa-check"></i> ${data.Message || 'No Image Found'}`;
            }
            else {
                badge.classList.add('in-progress');
                badge.textContent = data.Status;
            }
        }
    }
});
