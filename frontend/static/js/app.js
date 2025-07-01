// DupliGone Main Application JavaScript
class DupliGoneApp {
    constructor() {
        this.sessionId = null;
        this.jobId = null;
        this.selectedFiles = [];
        this.maxFileSize = 50 * 1024 * 1024; // 50MB
        this.maxFiles = 100;
        this.allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff'];
        
        this.initializeElements();
        this.attachEventListeners();
    }

    initializeElements() {
        // Get DOM elements
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.uploadBtn = document.getElementById('uploadBtn');
        this.filePreview = document.getElementById('filePreview');
        this.fileList = document.getElementById('fileList');
        this.clearFilesBtn = document.getElementById('clearFiles');
        this.startUploadBtn = document.getElementById('startUpload');
        
        this.uploadSection = document.getElementById('uploadSection');
        this.processingSection = document.getElementById('processingSection');
        this.resultsSection = document.getElementById('resultsSection');
        
        this.processingStatus = document.getElementById('processingStatus');
        this.progressFill = document.getElementById('progressFill');
        this.progressPercent = document.getElementById('progressPercent');
        this.progressDetail = document.getElementById('progressDetail');
        
        this.totalImages = document.getElementById('totalImages');
        this.clustersFound = document.getElementById('clustersFound');
        this.spaceSaved = document.getElementById('spaceSaved');
        
        this.viewResultsBtn = document.getElementById('viewResults');
        this.startOverBtn = document.getElementById('startOver');
        
        this.loadingOverlay = document.getElementById('loadingOverlay');
    }

    attachEventListeners() {
        // File input and upload area events
        this.uploadArea.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        
        // Drag and drop events
        this.uploadArea.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.uploadArea.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        this.uploadArea.addEventListener('drop', (e) => this.handleDrop(e));
        
        // Button events
        this.clearFilesBtn.addEventListener('click', () => this.clearFiles());
        this.startUploadBtn.addEventListener('click', () => this.startProcessing());
        this.viewResultsBtn.addEventListener('click', () => this.viewResults());
        this.startOverBtn.addEventListener('click', () => this.startOver());
    }

    handleDragOver(e) {
        e.preventDefault();
        this.uploadArea.classList.add('dragover');
    }

    handleDragLeave(e) {
        e.preventDefault();
        this.uploadArea.classList.remove('dragover');
    }

    handleDrop(e) {
        e.preventDefault();
        this.uploadArea.classList.remove('dragover');
        
        const files = Array.from(e.dataTransfer.files);
        this.processFiles(files);
    }

    handleFileSelect(e) {
        const files = Array.from(e.target.files);
        this.processFiles(files);
    }

    processFiles(files) {
        // Validate file count
        if (files.length > this.maxFiles) {
            this.showError(`Maximum ${this.maxFiles} files allowed. Selected: ${files.length}`);
            return;
        }

        // Filter and validate files
        const validFiles = [];
        const errors = [];

        files.forEach(file => {
            // Check file type
            if (!this.allowedTypes.includes(file.type)) {
                errors.push(`${file.name}: Invalid file type`);
                return;
            }

            // Check file size
            if (file.size > this.maxFileSize) {
                errors.push(`${file.name}: File too large (max 50MB)`);
                return;
            }

            // Check for duplicates
            const isDuplicate = this.selectedFiles.some(f => 
                f.name === file.name && f.size === file.size
            );
            
            if (!isDuplicate) {
                validFiles.push(file);
            }
        });

        // Show errors if any
        if (errors.length > 0) {
            this.showError(errors.join('\n'));
        }

        // Add valid files
        if (validFiles.length > 0) {
            this.selectedFiles = [...this.selectedFiles, ...validFiles];
            this.updateFilePreview();
        }
    }

    updateFilePreview() {
        if (this.selectedFiles.length === 0) {
            this.filePreview.style.display = 'none';
            return;
        }

        this.filePreview.style.display = 'block';
        this.fileList.innerHTML = '';

        this.selectedFiles.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';

            // Create image preview
            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            img.onload = () => URL.revokeObjectURL(img.src);

            // Create file info
            const fileInfo = document.createElement('div');
            fileInfo.className = 'file-info';
            fileInfo.innerHTML = `
                <div>${file.name}</div>
                <div>${this.formatFileSize(file.size)}</div>
            `;

            // Create remove button
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-btn';
            removeBtn.innerHTML = '<i class="fas fa-times"></i>';
            removeBtn.onclick = () => this.removeFile(index);

            fileItem.appendChild(img);
            fileItem.appendChild(fileInfo);
            fileItem.appendChild(removeBtn);
            this.fileList.appendChild(fileItem);
        });
    }

    removeFile(index) {
        this.selectedFiles.splice(index, 1);
        this.updateFilePreview();
    }

    clearFiles() {
        this.selectedFiles = [];
        this.fileInput.value = '';
        this.updateFilePreview();
    }

    async startProcessing() {
        if (this.selectedFiles.length === 0) {
            this.showError('Please select at least one image');
            return;
        }

        try {
            this.showLoading(true);

            // Step 1: Create session
            const sessionResponse = await fetch('/api/v1/sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!sessionResponse.ok) {
                throw new Error('Failed to create session');
            }

            const sessionData = await sessionResponse.json();
            this.sessionId = sessionData.session_id;

            // Step 2: Upload files
            const formData = new FormData();
            this.selectedFiles.forEach(file => {
                formData.append('files', file);
            });

            this.showProcessingSection();
            this.updateProgress(0, 'Uploading files...');

            const uploadResponse = await fetch(`/api/v1/sessions/${this.sessionId}/upload`, {
                method: 'POST',
                body: formData
            });

            if (!uploadResponse.ok) {
                throw new Error('Failed to upload files');
            }

            const uploadData = await uploadResponse.json();
            this.jobId = uploadData.job_id;

            // Step 3: Monitor processing
            this.updateProgress(10, 'Processing started...');
            this.monitorProcessing();

        } catch (error) {
            this.showError(`Processing failed: ${error.message}`);
            this.showLoading(false);
        }
    }

    async monitorProcessing() {
        if (!this.jobId) {
            this.showError('No job ID available');
            return;
        }

        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/v1/jobs/${this.jobId}/status`);
                
                if (!response.ok) {
                    throw new Error('Failed to get job status');
                }

                const jobStatus = await response.json();
                
                if (jobStatus.status === 'PROGRESS') {
                    const meta = jobStatus.result || {};
                    const progress = meta.current || 0;
                    const status = meta.status || 'Processing...';
                    
                    this.updateProgress(progress, status);
                    
                } else if (jobStatus.status === 'SUCCESS') {
                    clearInterval(pollInterval);
                    this.updateProgress(100, 'Processing complete!');
                    
                    // Get final results
                    setTimeout(() => {
                        this.getResults();
                    }, 1000);
                    
                } else if (jobStatus.status === 'FAILURE') {
                    clearInterval(pollInterval);
                    const error = jobStatus.result?.error || 'Processing failed';
                    this.showError(error);
                }
                
            } catch (error) {
                clearInterval(pollInterval);
                this.showError(`Monitoring failed: ${error.message}`);
            }
        }, 2000); // Poll every 2 seconds
    }

    async getResults() {
        try {
            const response = await fetch(`/api/v1/sessions/${this.sessionId}/results`);
            
            if (!response.ok) {
                throw new Error('Failed to get results');
            }

            const results = await response.json();
            this.displayResults(results);
            
        } catch (error) {
            this.showError(`Failed to get results: ${error.message}`);
        }
    }

    displayResults(results) {
        // Update result statistics
        this.totalImages.textContent = results.total_images || 0;
        this.clustersFound.textContent = results.clusters_found || 0;
        
        const spaceSavedMB = Math.round((results.potential_space_saved || 0) / (1024 * 1024));
        this.spaceSaved.textContent = `${spaceSavedMB} MB`;

        // Show results section
        this.showResultsSection();
    }

    showProcessingSection() {
        this.uploadSection.style.display = 'none';
        this.processingSection.style.display = 'block';
        this.resultsSection.style.display = 'none';
        this.showLoading(false);
    }

    showResultsSection() {
        this.uploadSection.style.display = 'none';
        this.processingSection.style.display = 'none';
        this.resultsSection.style.display = 'block';
    }

    updateProgress(percent, status) {
        this.progressFill.style.width = `${percent}%`;
        this.progressPercent.textContent = `${Math.round(percent)}%`;
        this.progressDetail.textContent = status;
        this.processingStatus.textContent = status;
    }

    viewResults() {
        if (this.sessionId) {
            window.location.href = `/results/${this.sessionId}`;
        }
    }

    startOver() {
        // Reset application state
        this.sessionId = null;
        this.jobId = null;
        this.selectedFiles = [];
        this.fileInput.value = '';
        
        // Reset UI
        this.uploadSection.style.display = 'block';
        this.processingSection.style.display = 'none';
        this.resultsSection.style.display = 'none';
        this.filePreview.style.display = 'none';
        
        // Reset progress
        this.updateProgress(0, 'Ready to start...');
    }

    showLoading(show) {
        this.loadingOverlay.style.display = show ? 'flex' : 'none';
    }

    showError(message) {
        alert(message); // Simple error display - can be enhanced with custom modal
        console.error('DupliGone Error:', message);
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new DupliGoneApp();
});
