# DupliGone Technical Report

## Overview
DupliGone is a full-stack photo deduplication and quality ranking system. It combines perceptual hashing, image quality analysis, and unsupervised clustering (DBSCAN) to group visually similar images, select the best shot in each group, and provide a user-friendly web interface for review and deletion. The backend is built with FastAPI, Celery, MongoDB, and Azure Blob Storage; the frontend is a modern, mobile-first web UI.

---

## 1. Image Hashing & Quality Analysis

- **Perceptual Hashing:**
  - Uses both pHash (robust to small changes, rotation, scaling) and dHash (robust to cropping, minor edits).
  - Each image is assigned a combined hash: `phash_dhash`.
  - Hash distance (Hamming) is used as a similarity metric.

- **Quality Metrics:**
  - **Sharpness:** Laplacian variance (higher = sharper).
  - **Brightness:** Mean pixel value.
  - **Contrast:** Pixel value standard deviation.
  - **Face Count:** Detected using OpenCV Haar cascades.
  - **Overall Score:** Weighted combination (tunable) to rank images within a cluster.

---

## 2. Clustering Logic

- **Distance Matrix:**
  - Pairwise hash distances are computed for all images in a session.
  - For combined hashes, the average of pHash and dHash distances is used.

- **DBSCAN Clustering:**
  - Unsupervised, density-based clustering (no need to specify number of clusters).
  - `eps` (distance threshold) is auto-tuned using the elbow method (k-distance graph + KneeLocator).
  - **Tuning for strict grouping:**
    - The elbow-detected `eps` is scaled down (e.g., 0.7x) and a minimum is enforced, so only truly similar images are grouped.
    - Fallbacks use lower percentiles/medians for even stricter separation.
  - **Noise Handling:** Images not similar to any others are treated as single-image clusters.

- **Cluster Output:**
  - Each cluster is a list of image indices.
  - For each cluster, the best image (highest quality score) is selected; others are flagged for deletion.

---

## 3. Backend Pipeline

- **Upload:**
  - Images are uploaded via FastAPI, stored in Azure Blob Storage, and indexed in MongoDB.
  - Each upload creates a session with a unique token.

- **Processing:**
  - Celery tasks process each image: download, hash, quality analysis, DB update.
  - After all images are processed, clustering is triggered.

- **Clustering:**
  - Clusters are saved in MongoDB, with best image and member IDs.
  - Each image is updated with its cluster ID and deletion recommendation.

- **Results API:**
  - `/getResult` returns all clusters, images, and recommendations for the session.
  - Secure SAS URLs are generated for image preview.

- **Deletion:**
  - User-selected images are deleted from both Azure and MongoDB.

- **Cleanup:**
  - A script removes old sessions, images, clusters, and orphaned blobs.

---

## 4. Frontend Logic

- **Cluster Stepper UI:**
  - Each cluster is shown one at a time, with navigation (Prev/Next).
  - The best image is highlighted; others can be toggled for deletion/retention.
  - User confirms deletions in batch.

- **Dry Run Mode:**
  - Users can preview what would be deleted without actually deleting files.

- **Visual Clarity:**
  - High-contrast backgrounds, clear button states, and responsive design for all devices.

---

## 5. How to Use

1. **Start the backend:**
   - Run FastAPI and Celery workers (see README for commands).
2. **Open the web UI:**
   - Go to the provided URL (usually http://localhost:8000).
3. **Upload images:**
   - Drag and drop or select files.
4. **Wait for processing:**
   - Progress is shown; clusters are computed in the background.
5. **Review clusters:**
   - Use the stepper to review each group, keep the best, and flag others for deletion.
6. **Delete or dry run:**
   - Confirm deletions, or use dry run to preview results.
7. **Cleanup:**
   - Use the provided script to remove old data and free up storage.

---

## 6. Technical Notes & Tuning

- **Clustering strictness** can be tuned in `services/image_processing.py` (see `find_optimal_eps_with_elbow`).
- **Quality metric weights** can be adjusted for your use case.
- **Database and storage** are cleaned up automatically, but you can run `scripts/cleanup.py` manually as needed.
- **Security:** All image access is via time-limited SAS URLs; sessions are tokenized.

---

## 7. Extensibility

- Add new quality metrics (e.g., ML-based content scoring).
- Integrate with other cloud storage providers.
- Add auto-tagging or scene detection for clusters.
- Improve UI/UX with more advanced review features.

---

For any technical deep-dive, see the code comments in each module. The logic is modular, testable, and designed for extensibility and clarity.
