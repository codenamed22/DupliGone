# Quick test to verify all our key packages are working
print("Testing imports...")

try:
    import fastapi
    print("✅ FastAPI imported successfully")
except ImportError as e:
    print(f"❌ FastAPI import failed: {e}")

try:
    import cv2
    print("✅ OpenCV imported successfully")
except ImportError as e:
    print(f"❌ OpenCV import failed: {e}")

try:
    import PIL
    print("✅ Pillow imported successfully")
except ImportError as e:
    print(f"❌ Pillow import failed: {e}")

try:
    import imagehash
    print("✅ ImageHash imported successfully")
except ImportError as e:
    print(f"❌ ImageHash import failed: {e}")

try:
    import pymongo
    print("✅ PyMongo imported successfully")
except ImportError as e:
    print(f"❌ PyMongo import failed: {e}")

try:
    import celery
    print("✅ Celery imported successfully")
except ImportError as e:
    print(f"❌ Celery import failed: {e}")

try:
    import azure.storage.blob
    print("✅ Azure Storage imported successfully")
except ImportError as e:
    print(f"❌ Azure Storage import failed: {e}")

print("\nIf you see all ✅ marks, you're ready to proceed!")
print("If you see any ❌ marks, we need to fix those dependencies first.")
