import imagehash
from PIL import Image
import os
from typing import Dict, List, Tuple
import numpy as np
from config.settings import settings

class ImageHasher:
    def __init__(self):
        self.hash_size = 8  # Standard hash size for perceptual hashing
        
    def compute_perceptual_hash(self, image_path: str) -> str:
        """Compute perceptual hash for an image using average hash"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Compute average hash (good for similar images)
                ahash = imagehash.average_hash(img, hash_size=self.hash_size)
                return str(ahash)
        except Exception as e:
            raise Exception(f"Failed to compute hash for {image_path}: {e}")
    
    def compute_difference_hash(self, image_path: str) -> str:
        """Compute difference hash for an image (better for cropped images)"""
        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                dhash = imagehash.dhash(img, hash_size=self.hash_size)
                return str(dhash)
        except Exception as e:
            raise Exception(f"Failed to compute dhash for {image_path}: {e}")
    
    def compute_wavelet_hash(self, image_path: str) -> str:
        """Compute wavelet hash (good for scaled images)"""
        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                whash = imagehash.whash(img, hash_size=self.hash_size)
                return str(whash)
        except Exception as e:
            raise Exception(f"Failed to compute whash for {image_path}: {e}")
    
    def compute_combined_hash(self, image_path: str) -> Dict[str, str]:
        """Compute multiple hash types for better similarity detection"""
        return {
            'ahash': self.compute_perceptual_hash(image_path),
            'dhash': self.compute_difference_hash(image_path),
            'whash': self.compute_wavelet_hash(image_path)
        }
    
    def calculate_hash_distance(self, hash1: str, hash2: str) -> int:
        """Calculate Hamming distance between two hashes"""
        try:
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            return h1 - h2  # Hamming distance
        except Exception as e:
            raise Exception(f"Failed to calculate hash distance: {e}")
    
    def are_images_similar(self, hash1: str, hash2: str, threshold: int = 5) -> bool:
        """Check if two images are similar based on hash distance"""
        distance = self.calculate_hash_distance(hash1, hash2)
        return distance <= threshold
    
    def batch_compute_hashes(self, image_paths: List[str]) -> Dict[str, Dict[str, str]]:
        """Compute hashes for multiple images"""
        results = {}
        for path in image_paths:
            try:
                results[path] = self.compute_combined_hash(path)
            except Exception as e:
                print(f"Warning: Failed to process {path}: {e}")
                continue
        return results

# Create global hasher instance
image_hasher = ImageHasher()
