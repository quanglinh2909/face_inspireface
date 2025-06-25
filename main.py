import atexit
import multiprocessing as mp
import os
import signal
import sys
import time
import traceback
from multiprocessing import shared_memory

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QGroupBox, QMessageBox
)

from one_process_face import run_face_processing


class CameraWidget(QWidget):
    def __init__(self, cam_id, rtsp):
        super().__init__()
        self.cam_id = cam_id
        self.rtsp = rtsp
        self.process = None
        self.shared_mem = None
        self.shared_mem_name = f"camera_{cam_id}_frame"

        # Kích thước frame
        self.frame_width = 640
        self.frame_height = 480
        self.frame_channels = 3
        self.frame_size = self.frame_width * self.frame_height * self.frame_channels

        self.label = QLabel("Camera {}".format(cam_id))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFixedSize(320, 240)  # Display size (scaled down from 640x480)
        self.label.setStyleSheet("border: 1px solid gray")

        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")

        self.btn_start.clicked.connect(self.start_camera)
        self.btn_stop.clicked.connect(self.stop_camera)

        layout = QVBoxLayout()
        layout.addWidget(self.label)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Timer để đọc frame từ shared memory
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        # Timer để kiểm tra trạng thái process
        self.health_check_timer = QTimer()
        self.health_check_timer.timeout.connect(self.check_process_health)

        # Flags
        self.is_running = False
        self.auto_restart_enabled = True
        self.last_frame_time = 0
        self.frame_timeout = 10  # seconds

    def start_camera(self):
        try:
            self._start_camera_process()

        except Exception as e:
            print(f"Error starting camera {self.cam_id}: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Error", f"Failed to start camera {self.cam_id}: {str(e)}")

    def _start_camera_process(self):
        """Internal method to start camera process"""
        # Cleanup any existing shared memory
        self._cleanup_shared_memory()

        # Start the face processing in a separate process
        self.process = mp.Process(
            target=run_face_processing,
            args=(self.cam_id, self.rtsp, self.shared_mem_name)
        )
        self.process.start()

        # Wait a bit for the process to start and create shared memory
        time.sleep(2)

        # Connect to shared memory
        self._connect_shared_memory()

        # Start timers
        self.timer.start(33)  # ~30 FPS
        self.health_check_timer.start(5000)  # Check every 5 seconds

        # Update UI
        self.is_running = True
        self.last_frame_time = time.time()
        self.label.setText("Camera {} is running...".format(self.cam_id))
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def stop_camera(self):
        try:
            # Disable auto restart
            self.auto_restart_enabled = False
            self.is_running = False

            # Stop timers
            self.timer.stop()
            self.health_check_timer.stop()

            # Terminate process
            if self.process and self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=5)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join()

            # Cleanup shared memory
            self._cleanup_shared_memory()

            self.label.clear()
            self.label.setText("Camera {}".format(self.cam_id))
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

        except Exception as e:
            print(f"Error stopping camera {self.cam_id}: {e}")

    def check_process_health(self):
        """Check if process is still alive and restart if needed"""
        if not self.is_running or not self.auto_restart_enabled:
            return

        try:
            # Check if process is alive
            process_alive = self.process and self.process.is_alive()

            # Check if we're still receiving frames
            current_time = time.time()
            frames_timeout = (current_time - self.last_frame_time) > self.frame_timeout

            if not process_alive:
                print(f"[Camera {self.cam_id}] Process died, restarting...")
                self._restart_camera("Process died")
            elif frames_timeout and self.shared_mem:
                print(f"[Camera {self.cam_id}] No frames for {self.frame_timeout}s, restarting...")
                self._restart_camera("Frame timeout")

        except Exception as e:
            print(f"[Camera {self.cam_id}] Health check error: {e}")
            self._restart_camera(f"Health check error: {e}")

    def _restart_camera(self, reason):
        """Restart camera with reason"""
        if not self.auto_restart_enabled or not self.is_running:
            return

        print(f"[Camera {self.cam_id}] Restarting camera - Reason: {reason}")

        try:
            # Stop current process
            self.timer.stop()
            if self.process and self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=3)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join()

            # Cleanup shared memory
            self._cleanup_shared_memory()

            # Update UI
            self.label.setText(f"Camera {self.cam_id} restarting...")

            # Wait a bit before restart
            time.sleep(1)

            # Restart
            self._start_camera_process()

        except Exception as e:
            print(f"[Camera {self.cam_id}] Failed to restart: {e}")
            # If restart fails, show error and stop
            self.label.setText(f"Camera {self.cam_id} - Restart failed")
            self.is_running = False
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def _connect_shared_memory(self):
        """Kết nối với shared memory"""
        try:
            max_attempts = 20  # Increase attempts
            for attempt in range(max_attempts):
                try:
                    self.shared_mem = shared_memory.SharedMemory(
                        name=self.shared_mem_name,
                        create=False
                    )
                    print(f"Connected to shared memory: {self.shared_mem_name}")
                    return
                except FileNotFoundError:
                    if attempt < max_attempts - 1:
                        print(f"Attempt {attempt + 1}/{max_attempts} - Waiting for shared memory...")
                        time.sleep(0.5)
                        continue
                    else:
                        raise
        except Exception as e:
            print(f"Failed to connect to shared memory {self.shared_mem_name}: {e}")
            self.shared_mem = None

    def _cleanup_shared_memory(self):
        """Dọn dẹp shared memory"""
        if self.shared_mem:
            try:
                self.shared_mem.close()
                self.shared_mem = None
            except:
                pass

    def update_frame(self):
        """Đọc frame từ shared memory và cập nhật UI"""
        if self.shared_mem is None:
            return

        try:
            # Đọc frame từ shared memory
            frame_array = np.ndarray(
                (self.frame_height, self.frame_width, self.frame_channels),
                dtype=np.uint8,
                buffer=self.shared_mem.buf
            )

            # Check if frame is not black (has some content)
            if np.sum(frame_array) > 0:
                self.last_frame_time = time.time()  # Update last frame time

                # Convert BGR to RGB for Qt
                frame_rgb = cv2.cvtColor(frame_array, cv2.COLOR_BGR2RGB)

                # Convert to QImage
                h, w, ch = frame_rgb.shape
                bytes_per_line = ch * w
                qt_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)

                # Scale to fit label
                scaled_pixmap = QPixmap.fromImage(qt_image).scaled(
                    self.label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

                self.label.setPixmap(scaled_pixmap)

        except Exception as e:
            print(f"Error updating frame for camera {self.cam_id}: {e}")

    def closeEvent(self, event):
        """Handle widget close event"""
        self.auto_restart_enabled = False
        self.stop_camera()
        event.accept()


class MainWindow(QWidget):
    def __init__(self, camera_ids):
        super().__init__()
        self.setWindowTitle("Camera Viewer with Face Recognition")
        self.camera_widgets = []

        layout = QVBoxLayout()
        for cam_id, rtsp in camera_ids:
            group = QGroupBox(f"Camera {cam_id}")
            cam_widget = CameraWidget(cam_id, rtsp)
            self.camera_widgets.append(cam_widget)

            vbox = QVBoxLayout()
            vbox.addWidget(cam_widget)
            group.setLayout(vbox)
            layout.addWidget(group)

        # Add control buttons
        control_layout = QHBoxLayout()

        btn_start_all = QPushButton("Start All Cameras")
        btn_stop_all = QPushButton("Stop All Cameras")
        btn_toggle_auto_restart = QPushButton("Disable Auto Restart")

        btn_start_all.clicked.connect(self.start_all_cameras)
        btn_stop_all.clicked.connect(self.stop_all_cameras)
        btn_toggle_auto_restart.clicked.connect(self.toggle_auto_restart)

        # Store button reference for text changes
        self.btn_toggle_auto_restart = btn_toggle_auto_restart

        control_layout.addWidget(btn_start_all)
        control_layout.addWidget(btn_stop_all)
        control_layout.addWidget(btn_toggle_auto_restart)
        control_layout.addStretch()

        # Add status label
        self.status_label = QLabel("Auto Restart: Enabled")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        layout.addLayout(control_layout)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def start_all_cameras(self):
        """Start all cameras"""
        for widget in self.camera_widgets:
            if widget.btn_start.isEnabled():
                widget.auto_restart_enabled = True
                widget.start_camera()

    def stop_all_cameras(self):
        """Stop all cameras"""
        for widget in self.camera_widgets:
            if widget.btn_stop.isEnabled():
                widget.stop_camera()

    def toggle_auto_restart(self):
        """Toggle auto restart for all cameras"""
        # Check current state from first camera
        current_state = self.camera_widgets[0].auto_restart_enabled if self.camera_widgets else True
        new_state = not current_state

        # Apply to all cameras
        for widget in self.camera_widgets:
            widget.auto_restart_enabled = new_state

        # Update UI
        if new_state:
            self.btn_toggle_auto_restart.setText("Disable Auto Restart")
            self.status_label.setText("Auto Restart: Enabled")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.btn_toggle_auto_restart.setText("Enable Auto Restart")
            self.status_label.setText("Auto Restart: Disabled")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def closeEvent(self, event):
        """Handle main window close event"""
        self.stop_all_cameras()
        event.accept()


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    print("❌ Lỗi không mong muốn:", exc_value)
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    cleanup()
    os._exit(1)


def cleanup():
    print("🧹 Dọn dẹp tiến trình con...")
    # Cleanup any remaining shared memory
    try:
        import psutil
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except:
                pass

        # Wait for children to terminate
        for child in children:
            try:
                child.wait(timeout=3)
            except:
                try:
                    child.kill()
                except:
                    pass
    except ImportError:
        pass  # psutil not available
    except:
        pass


if __name__ == '__main__':
    # Set multiprocessing start method
    mp.set_start_method('spawn', force=True)

    app = QApplication(sys.argv)

    # Danh sách camera: 0, 1,... (tuỳ máy)
    camera_ids = [
        # (0, "rtsp://admin:Oryza%40123@192.168.104.218:554/cam/realmonitor?channel=1&subtype=0"),
        # (1, "rtsp://admin:Oryza%40123@192.168.103.38:554/cam/realmonitor?channel=1&subtype=0")
        (0, "rtsp://admin:Oryza123@192.168.104.189:554/cam/realmonitor?channel=1&subtype=0"),
        (1, "rtsp://admin:Oryza123@192.168.104.187:554/cam/realmonitor?channel=1&subtype=0")
    ]

    main_window = MainWindow(camera_ids)
    main_window.resize(800, 700)
    main_window.show()

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    sys.excepthook = handle_exception

    sys.exit(app.exec_())
