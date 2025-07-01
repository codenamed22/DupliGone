import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import pairwise_distances
from typing import Dict, List, Tuple, Set
import imagehash
from collections import defaultdict
from config.settings import settings

class ImageClustering:
    def __init__(self):
        self.similarity_threshold = settings.similarity_threshold
        self.min_samples = settings.cluster_min_samples
        
    def hash_to_binary_array(self, hash_str: str) -> np.ndarray:
        """Convert hash string to binary array for clustering"""
        try:
            hash_obj = imagehash.hex_to_hash(hash_str)
            return hash_obj.hash.flatten().astype(int)
        except Exception as e:
            print(f"Error converting hash {hash_str}: {e}")
            return np.zeros(64, dtype=int)  # Default 8x8 hash
    
    def calculate_hamming_distance_matrix(self, hashes: List[str]) -> np.ndarray:
        """Calculate pairwise Hamming distances between hashes"""
        binary_arrays = [self.hash_to_binary_array(h) for h in hashes]
        binary_matrix = np.array(binary_arrays)
        
        # Calculate Hamming distances
        distances = pairwise_distances(binary_matrix, metric='hamming')
        
        # Convert to actual bit differences (multiply by hash size)
        hash_size = binary_matrix.shape[1]
        distances = distances * hash_size
        
        return distances
    
    def cluster_by_similarity(self, image_hashes: Dict[str, str]) -> Dict[int, List[str]]:
        """Cluster images based on perceptual hash similarity using DBSCAN"""
        if len(image_hashes) < 2:
            return {0: list(image_hashes.keys())} if image_hashes else {}
        
        image_paths = list(image_hashes.keys())
        hashes = list(image_hashes.values())
        
        # Calculate distance matrix
        distance_matrix = self.calculate_hamming_distance_matrix(hashes)
        
        # Convert similarity threshold to distance threshold
        # (lower similarity threshold = higher distance threshold)
        distance_threshold = (1.0 - self.similarity_threshold) * 64  # Assuming 64-bit hash
        
        # Apply DBSCAN clustering
        clustering = DBSCAN(
            eps=distance_threshold,
            min_samples=self.min_samples,
            metric='precomputed'
        ).fit(distance_matrix)
        
        # Group images by cluster
        clusters = defaultdict(list)
        for i, label in enumerate(clustering.labels_):
            clusters[label].append(image_paths[i])
        
        # Convert defaultdict to regular dict
        return dict(clusters)
    
    def cluster_by_combined_hashes(self, image_combined_hashes: Dict[str, Dict[str, str]]) -> Dict[int, List[str]]:
        """Cluster images using multiple hash types for better accuracy"""
        if len(image_combined_hashes) < 2:
            return {0: list(image_combined_hashes.keys())} if image_combined_hashes else {}
        
        image_paths = list(image_combined_hashes.keys())
        
        # Create combined distance matrix using multiple hash types
        n_images = len(image_paths)
        combined_distances = np.zeros((n_images, n_images))
        
        hash_types = ['ahash', 'dhash', 'whash']
        weights = [0.4, 0.4, 0.2]  # Weight different hash types
        
        for hash_type, weight in zip(hash_types, weights):
            try:
                hashes = [image_combined_hashes[path].get(hash_type, '') for path in image_paths]
                if all(hashes):  # Only process if all hashes exist
                    distances = self.calculate_hamming_distance_matrix(hashes)
                    combined_distances += distances * weight
            except Exception as e:
                print(f"Warning: Error processing {hash_type}: {e}")
                continue
        
        # Normalize combined distances
        if np.max(combined_distances) > 0:
            combined_distances = combined_distances / np.max(combined_distances) * 64
        
        # Apply DBSCAN clustering
        distance_threshold = (1.0 - self.similarity_threshold) * 64
        
        clustering = DBSCAN(
            eps=distance_threshold,
            min_samples=self.min_samples,
            metric='precomputed'
        ).fit(combined_distances)
        
        # Group images by cluster
        clusters = defaultdict(list)
        for i, label in enumerate(clustering.labels_):
            clusters[label].append(image_paths[i])
        
        return dict(clusters)
    
    def find_similar_groups(self, image_hashes: Dict[str, str], threshold: int = 5) -> List[List[str]]:
        """Find groups of similar images using simple threshold-based approach"""
        similar_groups = []
        processed = set()
        
        image_paths = list(image_hashes.keys())
        
        for i, path1 in enumerate(image_paths):
            if path1 in processed:
                continue
            
            current_group = [path1]
            processed.add(path1)
            
            for j, path2 in enumerate(image_paths[i+1:], i+1):
                if path2 in processed:
                    continue
                
                try:
                    hash1 = imagehash.hex_to_hash(image_hashes[path1])
                    hash2 = imagehash.hex_to_hash(image_hashes[path2])
                    distance = hash1 - hash2
                    
                    if distance <= threshold:
                        current_group.append(path2)
                        processed.add(path2)
                        
                except Exception as e:
                    print(f"Error comparing {path1} and {path2}: {e}")
                    continue
            
            # Only add groups with more than one image
            if len(current_group) > 1:
                similar_groups.append(current_group)
        
        return similar_groups
    
    def merge_small_clusters(self, clusters: Dict[int, List[str]], min_cluster_size: int = 2) -> Dict[int, List[str]]:
        """Merge or remove clusters that are too small"""
        filtered_clusters = {}
        cluster_id = 0
        
        for label, images in clusters.items():
            if len(images) >= min_cluster_size:
                filtered_clusters[cluster_id] = images
                cluster_id += 1
            # Small clusters (singletons) are ignored - they're unique images
        
        return filtered_clusters
    
    def get_cluster_statistics(self, clusters: Dict[int, List[str]]) -> Dict[str, any]:
        """Calculate clustering statistics"""
        total_images = sum(len(images) for images in clusters.values())
        total_clusters = len(clusters)
        
        cluster_sizes = [len(images) for images in clusters.values()]
        avg_cluster_size = np.mean(cluster_sizes) if cluster_sizes else 0
        max_cluster_size = max(cluster_sizes) if cluster_sizes else 0
        
        # Calculate potential savings (images that could be deleted)
        potential_deletions = sum(len(images) - 1 for images in clusters.values() if len(images) > 1)
        
        return {
            'total_images': total_images,
            'total_clusters': total_clusters,
            'average_cluster_size': avg_cluster_size,
            'max_cluster_size': max_cluster_size,
            'potential_deletions': potential_deletions,
            'cluster_size_distribution': cluster_sizes
        }

# Create global clustering instance
image_clusterer = ImageClustering()
