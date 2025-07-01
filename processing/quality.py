import cv2
import numpy as np
from PIL import Image
from typing import Dict, List, Tuple
import os
from config.settings import settings

class QualityAssessment:
    def __init__(self):
        self.sharpness_weight = settings.quality_weights_sharpness
        self.exposure_weight = settings.quality_weights_exposure
        self.faces_weight = settings.quality_weights_faces
        
        # Initialize face detection (optional)
        try:
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            self.face_detection_available = True
        except:
            self.face_detection_available = False
            print("Warning: Face detection not available")
    
    def calculate_sharpness(self, image_path: str) -> float:
        """Calculate image sharpness using Laplacian variance"""
        try:
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                raise Exception(f"Could not read image: {image_path}")
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Calculate Laplacian variance (higher = sharper)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            # Normalize to 0-1 scale (approximate)
            normalized_sharpness = min(laplacian_var / 1000.0, 1.0)
            
            return normalized_sharpness
            
        except Exception as e:
            print(f"Error calculating sharpness for {image_path}: {e}")
            return 0.0
    
    def calculate_exposure_quality(self, image_path: str) -> float:
        """Calculate exposure quality based on histogram analysis"""
        try:
            img = cv2.imread(image_path)
            if img is None:
                raise Exception(f"Could not read image: {image_path}")
            
            # Convert to grayscale for histogram analysis
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Calculate histogram
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist = hist.flatten()
            
            # Normalize histogram
            hist = hist / hist.sum()
            
            # Calculate metrics
            mean_brightness = np.average(range(256), weights=hist)
            
            # Penalize over/under exposure
            # Good exposure should have mean around 128 (middle gray)
            exposure_score = 1.0 - abs(mean_brightness - 128) / 128
            
            # Check for clipping (pure black or white)
            black_clip = hist[0]  # Pure black pixels
            white_clip = hist[255]  # Pure white pixels
            clipping_penalty = (black_clip + white_clip) * 2
            
            final_score = max(0.0, exposure_score - clipping_penalty)
            
            return final_score
            
        except Exception as e:
            print(f"Error calculating exposure for {image_path}: {e}")
            return 0.0
    
    def detect_faces(self, image_path: str) -> Tuple[int, float]:
        """Detect faces and return count and confidence score"""
        if not self.face_detection_available:
            return 0, 0.0
        
        try:
            img = cv2.imread(image_path)
            if img is None:
                return 0, 0.0
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            face_count = len(faces)
            
            # Calculate face quality score based on size and position
            if face_count == 0:
                return 0, 0.0
            
            # Score based on face size relative to image
            img_area = gray.shape[0] * gray.shape[1]
            total_face_area = sum(w * h for (x, y, w, h) in faces)
            face_ratio = total_face_area / img_area
            
            # Prefer images with faces that are 5-30% of image area
            if 0.05 <= face_ratio <= 0.3:
                face_score = 1.0
            elif face_ratio < 0.05:
                face_score = face_ratio / 0.05  # Small faces
            else:
                face_score = max(0.3, 1.0 - (face_ratio - 0.3) / 0.7)  # Large faces
            
            return face_count, face_score
            
        except Exception as e:
            print(f"Error detecting faces in {image_path}: {e}")
            return 0, 0.0
    
    def calculate_overall_quality(self, image_path: str) -> Dict[str, float]:
        """Calculate overall quality score combining all metrics"""
        try:
            # Get individual scores
            sharpness = self.calculate_sharpness(image_path)
            exposure = self.calculate_exposure_quality(image_path)
            face_count, face_score = self.detect_faces(image_path)
            
            # Calculate weighted overall score
            overall_score = (
                sharpness * self.sharpness_weight +
                exposure * self.exposure_weight +
                face_score * self.faces_weight
            )
            
            return {
                'sharpness': sharpness,
                'exposure': exposure,
                'face_count': face_count,
                'face_score': face_score,
                'overall_score': overall_score
            }
            
        except Exception as e:
            print(f"Error calculating quality for {image_path}: {e}")
            return {
                'sharpness': 0.0,
                'exposure': 0.0,
                'face_count': 0,
                'face_score': 0.0,
                'overall_score': 0.0
            }
    
    def rank_images_by_quality(self, image_paths: List[str]) -> List[Tuple[str, float]]:
        """Rank images by quality score (highest first)"""
        quality_scores = []
        
        for path in image_paths:
            quality_data = self.calculate_overall_quality(path)
            quality_scores.append((path, quality_data['overall_score']))
        
        # Sort by quality score (descending)
        quality_scores.sort(key=lambda x: x[1], reverse=True)
        
        return quality_scores
    
    def find_best_image(self, image_paths: List[str]) -> str:
        """Find the best quality image from a list"""
        if not image_paths:
            return None
        
        if len(image_paths) == 1:
            return image_paths[0]
        
        ranked_images = self.rank_images_by_quality(image_paths)
        return ranked_images[0][0]  # Return path of best image

# Create global quality assessment instance
quality_assessor = QualityAssessment()
