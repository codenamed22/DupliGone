"""
Image Processing service for DupliGone project.
Handles perceptual hashing (pHash + dHash), quality assessment,
and clustering with automatic eps detection using elbow method.
"""

import cv2
import numpy as np
from PIL import Image
import imagehash
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors
from typing import List, Dict, Tuple, Any
import io
import concurrent.futures
import threading
from dataclasses import dataclass
import matplotlib.pyplot as plt
from kneed import KneeLocator

@dataclass
class ImageAnalysis:
    phash_value: str
    dhash_value: str
    combined_hash: str
    quality_score: float
    sharpness: float
    brightness: float
    contrast: float
    face_count: int

class ImageProcessor:
    def __init__(self):
        # Load face detection cascade for quality assessment
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
    def calculate_perceptual_hashes(self, image_bytes: bytes) -> Dict[str, str]:
        """
        Calculate both pHash and dHash for better duplicate detection
        pHash: Good for rotated/scaled images
        dHash: Good for cropped/slightly modified images
        """
        image = Image.open(io.BytesIO(image_bytes))
        
        # Calculate both hash types
        phash = str(imagehash.phash(image, hash_size=8))
        dhash = str(imagehash.dhash(image, hash_size=8))
        
        # Create combined hash for better accuracy
        combined_hash = f"{phash}_{dhash}"
        
        return {
            "phash": phash,
            "dhash": dhash,
            "combined": combined_hash
        }
        
    def calculate_quality_metrics(self, image_bytes: bytes) -> Dict[str, float]:
        """
        Calculate various quality metrics for ranking images in clusters
        """
        # Convert bytes to OpenCV format
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {"sharpness": 0.0, "brightness": 0.0, "contrast": 0.0, "face_count": 0}
        
        # Calculate sharpness using Laplacian variance (higher = sharper)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Calculate brightness (mean of all pixels)
        brightness = np.mean(img)
        
        # Calculate contrast (standard deviation of pixel values)
        contrast = np.std(img)
        
        # Detect faces for portrait quality assessment
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
        face_count = len(faces)
        
        return {
            "sharpness": float(sharpness),
            "brightness": float(brightness),
            "contrast": float(contrast),
            "face_count": int(face_count)
        }
        
    def calculate_overall_quality(self, metrics: Dict[str, float]) -> float:
        """
        Calculate overall quality score from individual metrics
        Used to rank images within clusters and identify the best one
        """
        # Weight factors for different quality aspects
        sharpness_weight = 0.4  # Most important for photo quality
        brightness_weight = 0.2
        contrast_weight = 0.2
        face_weight = 0.2  # Bonus for portraits
        
        # Normalize sharpness (higher is better, typical range 0-1000)
        normalized_sharpness = min(metrics["sharpness"] / 100.0, 1.0)
        
        # Normalize brightness (optimal around 127 for 8-bit images)
        normalized_brightness = 1.0 - abs(metrics["brightness"] - 127) / 127.0
        
        # Normalize contrast (higher is better, typical range 0-100)
        normalized_contrast = min(metrics["contrast"] / 50.0, 1.0)
        
        # Face bonus (more faces = higher quality for portraits)
        face_bonus = min(metrics["face_count"] * 0.2, 1.0)
        
        quality_score = (
            normalized_sharpness * sharpness_weight +
            normalized_brightness * brightness_weight +
            normalized_contrast * contrast_weight +
            face_bonus * face_weight
        )
        
        return min(quality_score, 1.0)
        
    def analyze_image(self, image_bytes: bytes) -> ImageAnalysis:
        """
        Perform complete image analysis: hashing + quality assessment
        """
        hashes = self.calculate_perceptual_hashes(image_bytes)
        metrics = self.calculate_quality_metrics(image_bytes)
        quality_score = self.calculate_overall_quality(metrics)
        
        return ImageAnalysis(
            phash_value=hashes["phash"],
            dhash_value=hashes["dhash"],
            combined_hash=hashes["combined"],
            quality_score=quality_score,
            sharpness=metrics["sharpness"],
            brightness=metrics["brightness"],
            contrast=metrics["contrast"],
            face_count=metrics["face_count"]
        )
        
    def calculate_hash_distance(self, hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two perceptual hashes
        Lower distance = more similar images
        """
        # Convert hex hashes to integers and calculate XOR
        int_hash1 = int(hash1, 16)
        int_hash2 = int(hash2, 16)
        return bin(int_hash1 ^ int_hash2).count('1')
        
    def find_optimal_eps_with_elbow(self, distances: List[float]) -> float:
        """
        Use elbow method with k-distance graph to find optimal eps for DBSCAN
        This automatically determines the best clustering threshold
        """
        if len(distances) < 4:
            return 0.5  # Default fallback for small datasets
            
        # Create k-distance graph (k=4 is common for DBSCAN)
        k = min(4, len(distances) - 1)
        
        # Use NearestNeighbors to find k-distances
        nn = NearestNeighbors(n_neighbors=k, metric='precomputed')
        
        # Create distance matrix
        n = len(distances)
        distance_matrix = np.zeros((n, n))
        
        # Fill distance matrix (symmetric)
        idx = 0
        for i in range(n):
            for j in range(i + 1, n):
                distance_matrix[i][j] = distances[idx]
                distance_matrix[j][i] = distances[idx]
                idx += 1
        
        # Fit nearest neighbors
        nn.fit(distance_matrix)
        
        # Get k-distances and sort them
        k_distances, _ = nn.kneighbors(distance_matrix)
        k_distances = np.sort(k_distances[:, k-1])  # Get k-th nearest neighbor distances
        
        # Use KneeLocator to find the elbow point
        try:
            knee_locator = KneeLocator(
                range(len(k_distances)), 
                k_distances, 
                curve='convex', 
                direction='increasing'
            )
            
            if knee_locator.elbow is not None:
                optimal_eps = k_distances[knee_locator.elbow]
                print(f"Elbow method found optimal eps: {optimal_eps}")
                return optimal_eps
            else:
                # Fallback: use 90th percentile
                return np.percentile(k_distances, 90)
                
        except Exception as e:
            print(f"Elbow detection failed: {e}, using fallback method")
            # Fallback: use median of k-distances
            return np.median(k_distances)
        
    def cluster_similar_images(self, hash_list: List[str], use_combined: bool = True) -> List[List[int]]:
        """
        Cluster images based on hash similarity using DBSCAN with automatic eps detection
        """
        if len(hash_list) < 2:
            return [[i] for i in range(len(hash_list))]
            
        # Choose which hash to use for clustering
        if use_combined and '_' in hash_list[0]:
            # Use combined hash for better accuracy
            working_hashes = hash_list
        else:
            # Use individual hash (fallback)
            working_hashes = hash_list
            
        # Calculate all pairwise distances
        distances = []
        for i in range(len(working_hashes)):
            for j in range(i + 1, len(working_hashes)):
                if use_combined and '_' in working_hashes[i]:
                    # For combined hashes, split and calculate average distance
                    hash1_parts = working_hashes[i].split('_')
                    hash2_parts = working_hashes[j].split('_')
                    
                    phash_dist = self.calculate_hash_distance(hash1_parts[0], hash2_parts[0])
                    dhash_dist = self.calculate_hash_distance(hash1_parts[1], hash2_parts[1])
                    
                    # Average the distances for combined similarity
                    avg_distance = (phash_dist + dhash_dist) / 2.0
                    distances.append(avg_distance)
                else:
                    # Single hash distance
                    distance = self.calculate_hash_distance(working_hashes[i], working_hashes[j])
                    distances.append(distance)
        
        # Find optimal eps using elbow method
        optimal_eps = self.find_optimal_eps_with_elbow(distances)
        
        print(f"Using eps={optimal_eps} for DBSCAN clustering")
        
        # Create distance matrix for DBSCAN
        n = len(working_hashes)
        distance_matrix = np.zeros((n, n))
        
        # Fill distance matrix
        idx = 0
        for i in range(n):
            for j in range(i + 1, n):
                distance_matrix[i][j] = distances[idx]
                distance_matrix[j][i] = distances[idx]
                idx += 1
        
        # Apply DBSCAN clustering with optimal eps
        clustering = DBSCAN(
            eps=optimal_eps, 
            min_samples=2,  # At least 2 images to form a cluster
            metric='precomputed'
        )
        cluster_labels = clustering.fit_predict(distance_matrix)
        
        # Group indices by cluster label
        clusters = {}
        for idx, label in enumerate(cluster_labels):
            if label == -1:  # Noise points (no cluster)
                clusters[f"single_{idx}"] = [idx]  # Each noise point is its own cluster
            else:
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(idx)
        
        # Return list of clusters (each cluster is a list of image indices)
        return list(clusters.values())

# Create global instance
image_processor = ImageProcessor()


'''

What this enhanced image processing service does:

Dual Hash Approach:

pHash: Better for rotated/scaled duplicates
dHash: Better for cropped/edited duplicates
Combined Hash: Uses both for maximum accuracy

Automatic DBSCAN Tuning:

K-distance graph: Plots distances to find natural clustering threshold
Elbow method: Automatically finds optimal eps value
KneeLocator: Uses mathematical elbow detection
Fallback methods: Multiple backup strategies if elbow detection fails

Quality Assessment:

Sharpness (Laplacian variance)
Brightness/exposure analysis
Contrast measurement
Face detection for portrait bonus

Clustering Flow:

Calculate pHash + dHash for all images
Compute pairwise distances between combined hashes
Use elbow method to find optimal eps automatically
Apply DBSCAN with optimal parameters
Group similar images into clusters

'''