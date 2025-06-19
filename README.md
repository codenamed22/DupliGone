# DupliGone

## Photo Library Cleaner

**Background:**
Every student’s phone or laptop accumulates thousands of photos—many near-duplicates from burst shots, screenshots, or minor edits. Manually curating this library is tedious.

**Your Mission:**
Create a **backend service + UI** that

1. **Scans** a folder (or imports via API) to index all images.
2. **Groups** visually similar photos (using perceptual hashing or embedding clustering).
3. **Ranks** each group’s images by quality (sharpness, exposure, face-detection score) and identifies the “best” shot.
4. **Deletes** (or flags for deletion) the rest—after user confirmation.

**MVP Requirements:**

* A scanner module that computes a pHash or dHash for every image and clusters them (e.g., via locality-sensitive hashing + k-means or DBSCAN).
* A photo-quality metric combining:

  * Edge/sharpness (Laplacian variance)
  * Brightness/exposure histogram
  * (Optional) Face-count or smile-score via a lightweight CV model
* A simple web or GUI where users:

  1. See each cluster’s thumbnail grid.
  2. Confirm/delete non-best images in batch.
* A “dry-run” mode that only flags candidates without deleting files.

**Evaluation Criteria:**

* **Grouping accuracy:** low false-positive/negative clustering.
* **Quality ranking:** does the selected “best” image align with human preference?
* **Usability:** clear cluster views, undo capability, performance on large libraries.
* **Stretch work (bonus):** auto-tag clusters by scene/content (landscape, portrait), integrate with cloud storage APIs.
