import os
import queue
import threading
import time
import cv2
import numpy as np
from multiprocessing import shared_memory

import requests
from ultralytics import YOLO

from align_face import extract_faces_with_alignment, draw_keypoints_and_boxes
from check_platform import get_os_name, PlatformEnum
from face_embedding import SimpleEmbeddingExtractor
import logging

# Giảm mức log của httpx xuống WARNING
logging.getLogger("httpx").setLevel(logging.WARNING)


def run_face_processing(id_camera, rtsp, shared_mem_name):
    """Function to run face processing in a separate process"""
    face_processor = OneProcessFace(id_camera, rtsp, shared_mem_name)
    face_processor.process_face()


class OneProcessFace:
    def __init__(self, id_camera, rtsp, shared_mem_name=None):
        self.id_camera = id_camera
        self.platform = get_os_name()

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.path_model_detect_face = os.path.join(self.script_dir, "weight/yolov8n-face.onnx")
        self.path_model_recognition = os.path.join(self.script_dir, "weight/w600k_r50.onnx")
        if self.platform != PlatformEnum.UBUNTU:
            self.path_model_detect_face = os.path.join(self.script_dir, "weight/yolov8n-face_rknn_model_640")
            self.path_model_recognition = os.path.join(self.script_dir, "weight/w600k_r50.rknn")

        self.rtsp = rtsp
        self.stopped = False
        self.shared_mem_name = shared_mem_name
        self.shared_mem = None

        # Kích thước frame cố định
        self.frame_width = 640
        self.frame_height = 480
        self.frame_channels = 3
        self.frame_size = self.frame_width * self.frame_height * self.frame_channels

        # Initialize these in process_face() to avoid pickle issues
        self.frame_queue = None
        self.yolo_model = None
        self.embedding_extractor = None

    def _setup_shared_memory(self):
        """Tạo shared memory cho việc chia sẻ frame"""
        if self.shared_mem_name:
            try:
                # Tạo shared memory
                self.shared_mem = shared_memory.SharedMemory(
                    name=self.shared_mem_name,
                    create=True,
                    size=self.frame_size
                )
                print(f"[Camera {self.id_camera}] Shared memory created: {self.shared_mem_name}")
            except FileExistsError:
                # Nếu đã tồn tại, kết nối với shared memory hiện có
                self.shared_mem = shared_memory.SharedMemory(
                    name=self.shared_mem_name,
                    create=False
                )
                print(f"[Camera {self.id_camera}] Connected to existing shared memory: {self.shared_mem_name}")

    def _cleanup_shared_memory(self):
        """Dọn dẹp shared memory"""
        if self.shared_mem:
            try:
                self.shared_mem.close()
                self.shared_mem.unlink()
                print(f"[Camera {self.id_camera}] Shared memory cleaned up")
            except:
                pass

    def _write_frame_to_shared_memory(self, frame):
        """Ghi frame vào shared memory"""
        if self.shared_mem is None:
            return

        try:
            # Resize frame về kích thước cố định
            resized_frame = cv2.resize(frame, (self.frame_width, self.frame_height))

            # Chuyển đổi sang numpy array và ghi vào shared memory
            frame_array = np.array(resized_frame, dtype=np.uint8)
            np.copyto(np.ndarray(
                (self.frame_height, self.frame_width, self.frame_channels),
                dtype=np.uint8,
                buffer=self.shared_mem.buf
            ), frame_array)
        except Exception as e:
            print(f"[Camera {self.id_camera}] Error writing to shared memory: {e}")

    def process_face(self):
        from find_face_service import find_face_service

        # Initialize objects that can't be pickled
        self.frame_queue = queue.Queue(maxsize=1)
        # Setup shared memory
        self._setup_shared_memory()

        try:
            self.yolo_model = YOLO(self.path_model_detect_face, task='pose')

            self.embedding_extractor = SimpleEmbeddingExtractor(self.platform, self.path_model_recognition)

            thread = threading.Thread(target=self.read_frames, daemon=True)
            thread.start()
            count = 0
            start_time = time.time()
            temp = 0
            id_current = None
            current_time = time.time()

            while not self.stopped:
                if not self.frame_queue.empty():
                    frame = self.frame_queue.get_nowait()
                    if self.platform != PlatformEnum.UBUNTU:
                        frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_NV12)

                    # # Face recognition processing
                    aligned_faces, results = extract_faces_with_alignment(frame, self.yolo_model)
                    for i, aligned_face in enumerate(aligned_faces):
                        embedding = self.embedding_extractor.extract_embedding_from_aligned_face(aligned_face)
                        if embedding is not None:
                            data = find_face_service.find_face(embedding)
                            if len(data) > 0:
                                similarity = data[0]['similarity_score']
                                # percentage = (similarity + 1) / 2 * 100  # chuẩn hóa từ [-1,1] về [0,100]
                                if similarity > 0.5:
                                    print(data)
                                    face_id = data[0]['face_id']
                                    if id_current == face_id and time.time() - current_time < 5:
                                        continue
                                    print(f"[Camera {self.id_camera}] Recognized face ID: {face_id}, similarity: {similarity}")
                                    id_current = face_id
                                    current_time = time.time()
                                    requests.get("http://192.168.103.97:8090/3")

                    # # Draw keypoints and boxes
                    count += 1
                    if time.time() - start_time > 1:
                        # print(f"[Camera {self.id_camera}] Processed {count} frames in the last second")
                        count = 0
                        start_time = time.time()
                        temp = count

                    # draw temp frames per second

                    cv2.putText(frame, f"FPS: {temp}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    draw_keypoints_and_boxes(frame, results)

                    # Write frame to shared memory for GUI display
                    self._write_frame_to_shared_memory(frame)

                time.sleep(0.01)

        except Exception as e:
            print(f"[Camera {self.id_camera}] Error in process_face: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._cleanup_shared_memory()
            # cv2.destroyAllWindows()

    def read_frames(self):
        if self.platform == PlatformEnum.UBUNTU:
            pipeline = f"rtspsrc location={self.rtsp} latency=100 ! queue ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink"
        else:
            pipeline = (
                f"rtspsrc location={self.rtsp} latency=0 drop-on-latency=true ! queue ! rtph264depay ! h264parse ! mppvideodec  "
                f"!  videorate ! video/x-raw,format=NV12,framerate=15/1 ! "
                f"appsink drop=true sync=false"
            )
        cap = cv2.VideoCapture(pipeline)

        if not cap.isOpened():
            print(f"[Camera {self.id_camera}] Không thể kết nối RTSP: {self.rtsp}")
            self.stopped = True
            return

        print(f"[Camera {self.id_camera}] RTSP connected successfully")

        while not self.stopped:
            ret, frame = cap.read()
            if ret:
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                try:
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    pass
            else:
                print(f"[Camera {self.id_camera}] Failed to read frame")
                time.sleep(0.1)

        cap.release()
        print(f"[Camera {self.id_camera}] Camera released")

    def stop(self):
        """Stop the face processing"""
        self.stopped = True


if __name__ == "__main__":
    rtsp_url = "rtsp://admin:Oryza%40123@192.168.104.218:554/cam/realmonitor?channel=1&subtype=0"
    run_face_processing(id_camera=1, rtsp=rtsp_url, shared_mem_name="camera_1_frame")
