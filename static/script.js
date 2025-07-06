/**
 * DupliGone - JavaScript Application
 * Handles file uploads, API communication, and user interface interactions
 * Mobile-first with progressive enhancement
 */

class DupliGoneApp {
    constructor() {
        // Application state
        this.token = null;
        this.sessionId = null;
        this.pollInterval = null;
        this.selectedFiles = [];
        this.currentResults = null;
        
        // Configuration
        this.config = {
            apiBaseUrl: window.location.origin,
            pollIntervalMs: 2000,
            maxFileSize: 50 * 1024 * 1024, // 50MB per file
            allowedTypes: ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp'],
            maxFiles: 100
        };
        
        // Initialize the application
        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        console.log('🚀 DupliGone App initializing...');
        this.setupEventListeners();
        this.setupDragAndDrop();
        this.showSection('upload-section');
        this.showToast('Welcome to DupliGone! Upload your photos to get started.', 'info');
    }

    /**
     * Set up all event listeners
     */
    setupEventListeners() {
        // File input handling
        const fileInput = document.getElementById('file-input');
        fileInput.addEventListener('change', (e) => this.handleFileSelect(e));

        // Action buttons
        const deleteRecommendedBtn = document.getElementById('delete-recommended');
        const downloadCleanBtn = document.getElementById('download-clean');
        const startOverBtn = document.getElementById('start-over');
        const retryBtn = document.getElementById('retry-button');

        deleteRecommendedBtn.addEventListener('click', () => this.deleteRecommended());
        downloadCleanBtn.addEventListener('click', () => this.downloadClean());
        startOverBtn.addEventListener('click', () => this.startOver());
        retryBtn.addEventListener('click', () => this.startOver());

        // Upload area click
        const uploadArea = document.getElementById('upload-area');
        uploadArea.addEventListener('click', () => fileInput.click());

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
    }

    /**
     * Set up drag and drop functionality
     */
    setupDragAndDrop() {
        const uploadArea = document.getElementById('upload-area');
        
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, this.preventDefaults, false);
            document.body.addEventListener(eventName, this.preventDefaults, false);
        });

        // Highlight drop area when item is dragged over it
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => {
                uploadArea.classList.remove('dragover');
            }, false);
        });

        // Handle dropped files
        uploadArea.addEventListener('drop', (e) => this.handleDrop(e), false);
    }

    /**
     * Prevent default drag behaviors
     */
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    /**
     * Handle keyboard shortcuts
     */
    handleKeyboardShortcuts(e) {
        // Escape key to cancel current operation
        if (e.key === 'Escape') {
            this.cancelCurrentOperation();
        }
        
        // Enter key to proceed with recommended deletions
        if (e.key === 'Enter' && e.ctrlKey) {
            const deleteBtn = document.getElementById('delete-recommended');
            if (deleteBtn && !deleteBtn.disabled) {
                this.deleteRecommended();
            }
        }
    }

    /**
     * Handle file drop
     */
    handleDrop(e) {
        const files = Array.from(e.dataTransfer.files);
        this.processSelectedFiles(files);
    }

    /**
     * Handle file selection from input
     */
    handleFileSelect(e) {
        const files = Array.from(e.target.files);
        this.processSelectedFiles(files);
    }

    /**
     * Process and validate selected files
     */
    processSelectedFiles(files) {
        console.log(`📁 Processing ${files.length} selected files`);
        
        // Filter valid image files
        const validFiles = files.filter(file => this.validateFile(file));
        
        if (validFiles.length === 0) {
            this.showToast('No valid image files selected. Please choose JPG, PNG, GIF, or WebP files.', 'error');
            return;
        }

        if (validFiles.length !== files.length) {
            const invalidCount = files.length - validFiles.length;
            this.showToast(`${invalidCount} invalid files were filtered out.`, 'warning');
        }

        if (validFiles.length > this.config.maxFiles) {
            this.showToast(`Too many files selected. Maximum ${this.config.maxFiles} files allowed.`, 'error');
            return;
        }

        this.selectedFiles = validFiles;
        this.updateFileStats();
        
        // Auto-start upload if files are selected
        setTimeout(() => this.uploadFiles(), 1000);
    }

    /**
     * Validate individual file
     */
    validateFile(file) {
        // Check file type
        if (!this.config.allowedTypes.includes(file.type)) {
            console.warn(`❌ Invalid file type: ${file.type}`);
            return false;
        }

        // Check file size
        if (file.size > this.config.maxFileSize) {
            console.warn(`❌ File too large: ${file.size} bytes`);
            return false;
        }

        return true;
    }

    /**
     * Update file selection statistics
     */
    updateFileStats() {
        const fileCount = document.getElementById('file-count');
        const uploadStats = document.getElementById('upload-stats');
        
        if (this.selectedFiles.length > 0) {
            fileCount.textContent = this.selectedFiles.length;
            uploadStats.style.display = 'block';
        } else {
            uploadStats.style.display = 'none';
        }
    }

    /**
     * Upload files to the server
     */
    async uploadFiles() {
        if (this.selectedFiles.length === 0) return;

        console.log(`📤 Starting upload of ${this.selectedFiles.length} files`);
        
        try {
            // Show upload progress
            this.showUploadProgress();
            
            // Create FormData
            const formData = new FormData();
            this.selectedFiles.forEach(file => {
                formData.append('files', file);
            });

            // Upload with progress tracking
            const xhr = await this.uploadWithProgress(formData);

            if (xhr.status < 200 || xhr.status >= 300) {
                throw new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`);
            }

            let result;
            try {
                result = JSON.parse(xhr.responseText);
            } catch (e) {
                throw new Error('Upload failed: Invalid JSON response');
            }
            console.log('✅ Upload successful:', result);
            
            // Store session information
            this.token = result.token;
            this.sessionId = result.session_id;

            // Show processing section and start polling
            this.showSection('processing-section');
            this.updateProcessingStats(result.total_images, 0);
            this.startPolling();

            this.showToast('Upload completed! Processing your images...', 'success');

        } catch (error) {
            console.error('❌ Upload failed:', error);
            this.showError('Upload failed. Please try again.', error.message);
        }
    }

    /**
     * Upload with progress tracking
     */
    async uploadWithProgress(formData) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    this.updateUploadProgress(percentComplete);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(xhr);
                } else {
                    reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                }
            });

            xhr.addEventListener('error', () => {
                reject(new Error('Network error during upload'));
            });

            xhr.open('POST', `${this.config.apiBaseUrl}/upload`);
            xhr.send(formData);
        });
    }

    /**
     * Show upload progress
     */
    showUploadProgress() {
        const uploadProgress = document.getElementById('upload-progress');
        uploadProgress.style.display = 'block';
        this.updateUploadProgress(0);
    }

    /**
     * Update upload progress bar
     */
    updateUploadProgress(percentage) {
        const progressFill = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-text');
        const uploadStatus = document.getElementById('upload-status');
        
        progressFill.style.width = `${percentage}%`;
        progressText.textContent = `${Math.round(percentage)}%`;
        
        if (percentage < 100) {
            uploadStatus.textContent = 'Uploading images...';
        } else {
            uploadStatus.textContent = 'Upload complete! Starting processing...';
        }
    }

    /**
     * Start polling for processing results
     */
    startPolling() {
        console.log('🔄 Starting result polling...');
        
        this.pollInterval = setInterval(async () => {
            try {
                await this.checkResults();
            } catch (error) {
                console.error('❌ Polling error:', error);
                this.stopPolling();
                this.showError('Failed to get processing status. Please refresh the page.', error.message);
            }
        }, this.config.pollIntervalMs);
    }

    /**
     * Stop polling
     */
    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
            console.log('⏹️ Polling stopped');
        }
    }

    /**
     * Check processing results - UPDATED WITH FIX
     */
    async checkResults() {
        if (!this.token) return;

        try {
            const response = await fetch(`${this.config.apiBaseUrl}/getResult`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`Failed to get results: ${response.status}`);
            }

            const result = await response.json();
            console.log('📊 Polling result:', result); // Add debug logging
            
            this.updateProcessingStatus(result);

            // **FIX: Handle all possible statuses**
            if (result.status === 'completed') {
                console.log('✅ Processing completed, showing results');
                this.stopPolling();
                this.showResults(result);
            } else if (result.status === 'failed') {
                console.log('❌ Processing failed');
                this.stopPolling();
                this.showError('Processing failed. Please try again.');
            } else {
                // **NEW: Continue polling for other statuses**
                console.log(`🔄 Status: ${result.status}, continuing to poll...`);
                // Keep polling for: uploading, uploaded, processing, clustering
            }
            
        } catch (error) {
            console.error('❌ Polling error:', error);
            this.stopPolling();
            this.showError('Failed to get processing status. Please refresh the page.', error.message);
        }
    }

    /**
     * Update processing status display - UPDATED WITH FIX
     */
    updateProcessingStatus(result) {
        this.updateProcessingStats(result.total_images, result.processed_images);
        
        const statusMessages = {
            'uploading': 'Uploading images...',
            'uploaded': 'Upload complete, starting analysis...',
            'processing': 'Analyzing image quality and finding duplicates...',
            'clustering': 'Grouping similar images using AI clustering...',
            'completed': 'Processing complete!'
        };

        const processingStatus = document.getElementById('processing-status');
        processingStatus.textContent = statusMessages[result.status] || `Processing... (${result.status})`;

        // Update clusters count if available
        if (result.clusters && result.clusters.length > 0) {
            const clustersCount = document.getElementById('clusters-count');
            if (clustersCount) {
                clustersCount.textContent = result.clusters.length;
            }
        }
        
        // **NEW: Add debug info**
        console.log(`📊 Status: ${result.status}, Processed: ${result.processed_images}/${result.total_images}`);
    }

    /**
     * Update processing statistics
     */
    updateProcessingStats(total, processed) {
        const totalCount = document.getElementById('total-count');
        const processedCount = document.getElementById('processed-count');
        
        totalCount.textContent = total;
        processedCount.textContent = processed;
    }

    /**
     * Show processing results
     */
    showResults(result) {
        console.log('📊 Showing results:', result);
        
        this.currentResults = result;
        this.showSection('results-section');
        
        // Update summary statistics
        this.updateSummaryStats(result);
        
        // Render clusters
        this.renderClusters(result.clusters);
        
        this.showToast('Processing complete! Review your results below.', 'success');
    }

    /**
     * Update summary statistics
     */
    updateSummaryStats(result) {
        const clustersFound = document.getElementById('clusters-found');
        const recommendedDeletions = document.getElementById('recommended-deletions');
        const spaceSaved = document.getElementById('space-saved');
        
        clustersFound.textContent = result.clusters.length;
        recommendedDeletions.textContent = result.recommendations.recommended_for_deletion;
        spaceSaved.textContent = result.recommendations.estimated_space_saved_mb || 0;
    }

    /**
     * Render image clusters
     */
    renderClusters(clusters) {
        const container = document.getElementById('clusters-container');
        container.innerHTML = '';

        if (clusters.length === 0) {
            container.innerHTML = `
                <div class="no-clusters">
                    <h3>🎉 No duplicates found!</h3>
                    <p>Your photo library is already clean. All images appear to be unique.</p>
                </div>
            `;
            return;
        }

        clusters.forEach((cluster, index) => {
            const clusterElement = this.createClusterElement(cluster, index);
            container.appendChild(clusterElement);
        });
    }

    /**
     * Create cluster HTML element
     */
    createClusterElement(cluster, index) {
        const clusterDiv = document.createElement('div');
        clusterDiv.className = 'cluster';
        clusterDiv.innerHTML = `
            <div class="cluster-header">
                <h3 class="cluster-title">Group ${index + 1} - ${cluster.total_images} similar images</h3>
                <div class="cluster-badges">
                    <span class="badge badge-best">1 Best</span>
                    <span class="badge badge-delete">${cluster.total_images - 1} Recommended for deletion</span>
                </div>
            </div>
            <div class="cluster-images" id="cluster-${cluster.cluster_id}">
                ${cluster.images.map(image => this.createImageElement(image, cluster.best_image_id)).join('')}
            </div>
        `;
        return clusterDiv;
    }

    /**
     * Create image HTML element
     */
    createImageElement(image, bestImageId) {
        const isBest = image.image_id === bestImageId;
        const qualityPercent = Math.round(image.quality_score * 100);
        
        return `
            <div class="image-item ${isBest ? 'best-image' : ''}" data-image-id="${image.image_id}">
                <img src="${image.blob_url}" alt="${image.original_filename}" loading="lazy" 
                     onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZGRkIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkltYWdlIEVycm9yPC90ZXh0Pjwvc3ZnPg=='">
                <div class="image-overlay">
                    <div class="image-info">
                        <div class="quality-score">${qualityPercent}%</div>
                        ${isBest ? '<div class="badge badge-best">Best Quality</div>' : ''}
                        ${image.delete_recommended ? '<div class="badge badge-delete">Delete?</div>' : ''}
                        <div class="image-filename">${image.original_filename}</div>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Delete recommended images
     */
    async deleteRecommended() {
        if (!this.currentResults) return;

        // Get all recommended images
        const recommendedImages = [];
        this.currentResults.clusters.forEach(cluster => {
            cluster.images.forEach(image => {
                if (image.delete_recommended) {
                    recommendedImages.push(image.image_id);
                }
            });
        });

        if (recommendedImages.length === 0) {
            this.showToast('No images recommended for deletion.', 'info');
            return;
        }

        // Confirm deletion
        const confirmed = confirm(
            `Are you sure you want to delete ${recommendedImages.length} recommended images? This action cannot be undone.`
        );
        
        if (!confirmed) return;

        try {
            this.showLoadingOverlay('Deleting images...');

            const response = await fetch(`${this.config.apiBaseUrl}/delete`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.token}`
                },
                body: JSON.stringify({
                    image_ids: recommendedImages
                })
            });

            if (!response.ok) {
                throw new Error(`Delete failed: ${response.status}`);
            }

            const result = await response.json();
            console.log('✅ Delete successful:', result);

            // Remove deleted images from UI
            recommendedImages.forEach(imageId => {
                const element = document.querySelector(`[data-image-id="${imageId}"]`);
                if (element) {
                    element.style.animation = 'fadeOut 0.3s ease-out';
                    setTimeout(() => element.remove(), 300);
                }
            });

            // Update summary stats
            const currentRecommended = parseInt(document.getElementById('recommended-deletions').textContent);
            document.getElementById('recommended-deletions').textContent = Math.max(0, currentRecommended - result.deleted_count);

            this.hideLoadingOverlay();
            this.showToast(`Successfully deleted ${result.deleted_count} images!`, 'success');

        } catch (error) {
            console.error('❌ Delete failed:', error);
            this.hideLoadingOverlay();
            this.showToast('Failed to delete images. Please try again.', 'error');
        }
    }

    /**
     * Download clean library (placeholder)
     */
    downloadClean() {
        // This would implement downloading the cleaned library
        // For now, show a message about the feature
        this.showToast('Download feature will be implemented based on your storage preferences.', 'info');
        
        // In a real implementation, this would:
        // 1. Create a zip file of remaining images
        // 2. Trigger download
        // 3. Or provide links to remaining images in cloud storage
    }

    /**
     * Start over - reset the application
     */
    startOver() {
        // Reset application state
        this.token = null;
        this.sessionId = null;
        this.selectedFiles = [];
        this.currentResults = null;
        
        // Stop any ongoing polling
        this.stopPolling();
        
        // Reset UI
        this.showSection('upload-section');
        this.updateFileStats();
        
        // Reset file input
        const fileInput = document.getElementById('file-input');
        fileInput.value = '';
        
        // Hide progress
        const uploadProgress = document.getElementById('upload-progress');
        uploadProgress.style.display = 'none';
        
        this.showToast('Ready for new photos!', 'info');
    }

    /**
     * Cancel current operation
     */
    cancelCurrentOperation() {
        this.stopPolling();
        this.hideLoadingOverlay();
        this.showToast('Operation cancelled.', 'info');
    }

    /**
     * Show specific section
     */
    showSection(sectionId) {
        // Hide all sections
        document.querySelectorAll('.section').forEach(section => {
            section.classList.remove('active');
        });
        
        // Show target section
        const targetSection = document.getElementById(sectionId);
        if (targetSection) {
            targetSection.classList.add('active');
        }
    }

    /**
     * Show error section
     */
    showError(message, details = '') {
        const errorMessage = document.getElementById('error-message');
        errorMessage.textContent = message;
        
        if (details) {
            console.error('Error details:', details);
        }
        
        this.showSection('error-section');
        this.showToast(message, 'error');
    }

    /**
     * Show loading overlay
     */
    showLoadingOverlay(message = 'Processing...') {
        const overlay = document.getElementById('loading-overlay');
        const text = overlay.querySelector('p');
        text.textContent = message;
        overlay.style.display = 'flex';
    }

    /**
     * Hide loading overlay
     */
    hideLoadingOverlay() {
        const overlay = document.getElementById('loading-overlay');
        overlay.style.display = 'none';
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info', duration = 5000) {
        const container = document.getElementById('toast-container');
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        
        container.appendChild(toast);
        
        // Auto-remove toast
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    }
}

// Add slideOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeOut {
        from { opacity: 1; transform: scale(1); }
        to { opacity: 0; transform: scale(0.8); }
    }
    
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    
    .no-clusters {
        text-align: center;
        padding: 3rem;
        background: var(--gray-50);
        border-radius: var(--radius-lg);
        border: 2px dashed var(--gray-300);
    }
    
    .no-clusters h3 {
        color: var(--success-color);
        margin-bottom: 1rem;
        font-size: 1.5rem;
    }
    
    .no-clusters p {
        color: var(--gray-600);
    }
`;
document.head.appendChild(style);

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('🎯 DOM loaded, initializing DupliGone...');
    window.dupliGoneApp = new DupliGoneApp();
});

// Handle page visibility changes (pause polling when tab is hidden)
document.addEventListener('visibilitychange', () => {
    if (window.dupliGoneApp) {
        if (document.hidden) {
            console.log('📱 Tab hidden, pausing operations');
        } else {
            console.log('📱 Tab visible, resuming operations');
        }
    }
});

// Handle online/offline status
window.addEventListener('online', () => {
    if (window.dupliGoneApp) {
        window.dupliGoneApp.showToast('Connection restored!', 'success');
    }
});

window.addEventListener('offline', () => {
    if (window.dupliGoneApp) {
        window.dupliGoneApp.showToast('Connection lost. Please check your internet.', 'error');
    }
});
