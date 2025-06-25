# main.py
import os
import warnings

from fastapi import HTTPException
from ultralytics import YOLO

from align_face import extract_faces_with_alignment
from check_platform import PlatformEnum, get_os_name
from face_embedding import SimpleEmbeddingExtractor

# Suppress FutureWarning from InsightFace before importing
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*rcond parameter will change.*")

import cv2
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid
from typing import List, Optional
import logging
from PIL import Image
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FaceRecognitionService:
    def __init__(self):
        # Initialize Qdrant client
        self.qdrant_client = QdrantClient(
            host="localhost",
            port=6333
        )
        self.platform = get_os_name()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.path_model_detect_face = os.path.join(self.script_dir, "weight/yolov8n-face.onnx")
        self.path_model_recognition = os.path.join(self.script_dir, "weight/w600k_r50.onnx")
        if self.platform != PlatformEnum.UBUNTU:
            self.path_model_detect_face = os.path.join(self.script_dir, "weight/yolov8n-face_rknn_model_640")
            self.path_model_recognition = os.path.join(self.script_dir, "weight/w600k_r50.rknn")

        self.yolo_model = YOLO(self.path_model_detect_face, task='pose')
        self.embedding_extractor = SimpleEmbeddingExtractor(self.platform, self.path_model_recognition)

        # Collection name
        self.collection_name = "face_embeddings"

        # Create collection if not exists
        self._create_collection()

    def _create_collection(self):
        """Create Qdrant collection for face embeddings"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.collection_name not in collection_names:
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=512,  # InsightFace embedding size
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise e

    def extract_face_embedding(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """Extract face embedding from image bytes"""
        try:

            # Convert bytes to image
            image = Image.open(io.BytesIO(image_bytes))
            image_array = np.array(image)

            # Convert RGB to BGR for OpenCV
            if len(image_array.shape) == 3 and image_array.shape[2] == 3:
                image_array = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)

            # Detect faces and extract embeddings
            aligned_faces, results = extract_faces_with_alignment(image_array, self.yolo_model)

            if len(aligned_faces) == 0:
                return None
            embedding = self.embedding_extractor.extract_embedding_from_aligned_face(aligned_faces[0])
            # Return embedding of the first detected face
            return embedding

        except Exception as e:
            logger.error(f"Error extracting face embedding: {e}")
            return None

    def add_face(self, image_bytes: bytes, person_name: str) -> dict:
        """Add face to database"""
        embedding = self.extract_face_embedding(image_bytes)

        if embedding is None:
            raise HTTPException(status_code=400, detail="No face detected in image")

        # Ensure embedding is 1D and convert to list
        if embedding.ndim > 1:
            embedding = embedding.flatten()

        # Generate unique ID
        face_id = str(uuid.uuid4())

        # Store in Qdrant
        try:
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=face_id,
                        vector=embedding.tolist(),
                        payload={
                            "person_name": person_name,
                            "face_id": face_id
                        }
                    )
                ]
            )

            return {
                "face_id": face_id,
                "person_name": person_name,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Error storing face: {e}")
            raise HTTPException(status_code=500, detail="Failed to store face")

    def search_face(self, image_bytes: bytes, limit: int = 5) -> List[dict]:
        """Search for similar faces"""
        embedding = self.extract_face_embedding(image_bytes)

        if embedding is None:
            raise HTTPException(status_code=400, detail="No face detected in image")

        # Ensure embedding is 1D
        if embedding.ndim > 1:
            embedding = embedding.flatten()

        try:
            # Search in Qdrant
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=embedding.tolist(),
                limit=limit
            )

            results = []
            for result in search_results:
                results.append({
                    "face_id": result.payload["face_id"],
                    "person_name": result.payload["person_name"],
                    "similarity_score": result.score
                })

            return results

        except Exception as e:
            logger.error(f"Error searching faces: {e}")
            raise HTTPException(status_code=500, detail="Failed to search faces")

    def find_face(self, embedding, limit: int = 1) -> List[dict]:
        # Ensure embedding is 1D
        if embedding.ndim > 1:
            embedding = embedding.flatten()

        try:
            # Search in Qdrant
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=embedding.tolist(),
                limit=limit
            )

            results = []
            for result in search_results:
                results.append({
                    "face_id": result.payload["face_id"],
                    "person_name": result.payload["person_name"],
                    "similarity_score": result.score
                })

            return results

        except Exception as e:
            results = []

    def get_all_faces(self) -> List[dict]:
        """Get all stored faces"""
        try:
            # Scroll through all points
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                limit=100
            )

            faces = []
            for point in scroll_result[0]:
                faces.append({
                    "face_id": point.payload["face_id"],
                    "person_name": point.payload["person_name"]
                })

            return faces

        except Exception as e:
            logger.error(f"Error getting all faces: {e}")
            raise HTTPException(status_code=500, detail="Failed to get faces")

    def delete_face(self, face_id: str) -> dict:
        """Delete a face from database"""
        try:
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=[face_id]
            )

            return {
                "face_id": face_id,
                "status": "deleted"
            }

        except Exception as e:
            logger.error(f"Error deleting face: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete face")


face_service = FaceRecognitionService()
