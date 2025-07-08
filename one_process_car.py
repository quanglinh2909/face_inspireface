import logging
import os
import queue
import threading
import time
from multiprocessing import shared_memory

import cv2
import numpy as np
import requests
from ultralytics import YOLO

from check_platform import get_os_name, PlatformEnum
from shapely.geometry import Polygon, box as shapely_box

# Giảm mức log của httpx xuống WARNING
logging.getLogger("httpx").setLevel(logging.WARNING)


def run_vehicle_processing(id_camera, rtsp, shared_mem_name, lane, url_parking, data):
    """Function to run face processing in a separate process"""
    face_processor = OneProcessVehicle(id_camera, rtsp, shared_mem_name, lane, url_parking, data)
    face_processor.process_face()


class OneProcessVehicle:
    def __init__(self, id_camera, rtsp, shared_mem_name=None, lane="left", url_parking=None, polygon_detect=[]):
        self.id_camera = id_camera
        self.platform = get_os_name()
        self.lane = lane  # Thêm lane vào constructor
        self.url_parking = url_parking
        self.polygon_detect = polygon_detect

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.path_model_detect_vehicle = os.path.join(self.script_dir, "weight/yolov8n.onnx")
        if self.platform != PlatformEnum.UBUNTU:
            self.path_model_detect_vehicle = os.path.join(self.script_dir, "weight/yolov8n_rknn")

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

        # Initialize objects that can't be pickled
        self.frame_queue = queue.Queue(maxsize=1)
        # Setup shared memory
        self._setup_shared_memory()
        print("[Camera {self.id_camera}] Shared memory setup complete")

        try:
            self.yolo_model = YOLO(self.path_model_detect_vehicle, task='detect')

            thread = threading.Thread(target=self.read_frames, daemon=True)
            thread.start()
            start_time = time.time()

            while not self.stopped:
                if not self.frame_queue.empty():
                    frame = self.frame_queue.get_nowait()
                    if self.platform != PlatformEnum.UBUNTU:
                        frame = cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_NV12)
                        # Run YOLO inference on the frame
                    results = self.yolo_model(frame, verbose=False, classes=[2], conf=0.6, iou=0.1)

                    # draw the polygon area for detection
                    cv2.polylines(frame, [np.array(self.polygon_detect, np.int32)], isClosed=True,
                                  color=(255, 0, 0),
                                  thickness=2)

                    for result in results:
                        boxes = result.boxes.numpy()
                        for b in boxes:
                            x1, y1, x2, y2 = map(int, b.xyxy[0])

                            bbox_polygon = shapely_box(x1, y1, x2, y2)
                            intersection = Polygon(self.polygon_detect).intersection(bbox_polygon)
                            intersection_area = intersection.area
                            if intersection_area == 0:
                                # draw bounding box red
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                            else:
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                                if time.time() - start_time > 10:
                                    start_time = time.time()
                                    print("Intersection area:", intersection_area)
                                    try:

                                        result = requests.post(f"{self.url_parking}/barrier/open",
                                                               json={"io_pin": 3})

                                    except Exception as e:
                                        print(f"[Camera {self.id_camera}] Error sending data: {e}")
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
    # run_face_processing(id_camera=1, rtsp=rtsp_url, shared_mem_name="camera_1_frame")
