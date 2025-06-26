# main.py
import os
import warnings

from fastapi import HTTPException
from ultralytics import YOLO

from align_face import extract_faces_with_alignment
from check_platform import PlatformEnum, get_os_name
from face_embedding import SimpleEmbeddingExtractor


import cv2
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FaceRecognitionService:
    def __init__(self):
        # Initialize Qdrant client
        self.qdrant_client = QdrantClient(
            host="localhost",
            port=6333
        )
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
                    "similarity_score": result.score,
                    "code_card": result.payload.get("code_card"),
                })

            return results

        except Exception as e:
            results = []


find_face_service = FaceRecognitionService()
