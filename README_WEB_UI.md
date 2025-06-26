# Face Recognition System - Giao diện Web

Hệ thống nhận diện khuôn mặt với giao diện web được xây dựng bằng FastAPI và Jinja2.

## Tính năng chính

### 🏠 Trang chủ
- Hiển thị tổng quan hệ thống
- Thống kê nhanh về số lượng khuôn mặt
- Điều hướng nhanh đến các chức năng

### 👥 Quản lý khuôn mặt
- **Xem danh sách**: Hiển thị tất cả khuôn mặt dưới dạng lưới (grid)
- **Tìm kiếm**: Lọc theo tên người hoặc mã thẻ
- **Sửa thông tin**: Cập nhật tên, mã thẻ, hoặc thay đổi ảnh
- **Xóa khuôn mặt**: Xóa khỏi hệ thống với xác nhận

### ➕ Thêm khuôn mặt mới
- Upload ảnh với preview trực tiếp
- Nhập thông tin tên người và mã thẻ
- Validation ảnh (định dạng, kích thước)
- Phản hồi kết quả real-time

### 🔍 Tìm kiếm khuôn mặt
- Upload ảnh để tìm khuôn mặt tương tự
- Hiển thị kết quả với độ tin cậy (confidence score)
- Tùy chỉnh số lượng kết quả
- Sắp xếp theo độ tương tự

### 📊 Thông tin hệ thống
- Thống kê chi tiết về collection
- Kiểm tra tình trạng các service
- Xuất thông tin hệ thống
- Làm mới dữ liệu

## Cấu trúc Routes

### API Routes (JSON Response)
```
GET  /api                  # API status
POST /add_face            # Thêm khuôn mặt
POST /search_face         # Tìm kiếm khuôn mặt  
GET  /faces               # Danh sách khuôn mặt
PUT  /faces/{face_id}     # Cập nhật khuôn mặt
DELETE /faces/{face_id}   # Xóa khuôn mặt
GET  /collection_info     # Thông tin collection
```

### Web UI Routes (HTML Response)
```
GET /                     # Redirect to /ui
GET /ui                   # Trang chủ
GET /faces/ui             # Quản lý khuôn mặt
GET /add                  # Thêm khuôn mặt
GET /search               # Tìm kiếm
GET /info                 # Thông tin hệ thống
```

### Static Files
```
/static/css/custom.css    # CSS tùy chỉnh
/static/js/app.js         # JavaScript tùy chỉnh
/images/                  # Thư mục chứa ảnh
```

## Công nghệ sử dụng

### Backend
- **FastAPI**: Web framework hiện đại, nhanh
- **Jinja2**: Template engine cho HTML
- **InsightFace**: Thư viện nhận diện khuôn mặt
- **Qdrant**: Vector database cho embedding
- **OpenCV**: Xử lý ảnh
- **Pillow**: Thao tác ảnh

### Frontend
- **Bootstrap 5**: CSS framework responsive
- **Font Awesome**: Icon library
- **Vanilla JavaScript**: Tương tác người dùng
- **CSS3**: Animations và styling

## Cài đặt và chạy

1. **Cài đặt dependencies**:
```bash
pip install -r requirements.txt
```

2. **Khởi động Qdrant** (nếu chưa có):
```bash
docker-compose up -d
```

3. **Chạy server**:
```bash
python server.py
```

4. **Truy cập giao diện**:
- Web UI: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Hướng dẫn sử dụng

### Thêm khuôn mặt mới
1. Truy cập `/add` hoặc click "Thêm mới"
2. Điền thông tin tên người và mã thẻ
3. Chọn ảnh khuôn mặt (JPG, PNG)
4. Click "Lưu khuôn mặt"
5. Hệ thống sẽ xử lý và hiển thị kết quả

### Quản lý khuôn mặt
1. Truy cập `/faces/ui` hoặc click "Quản lý"
2. Xem danh sách tất cả khuôn mặt
3. Sử dụng ô tìm kiếm để lọc
4. Click biểu tượng bút chì để sửa
5. Click biểu tượng thùng rác để xóa

### Tìm kiếm khuôn mặt
1. Truy cập `/search` hoặc click "Tìm kiếm"
2. Upload ảnh cần tìm
3. Chọn số lượng kết quả mong muốn
4. Click "Tìm kiếm khuôn mặt"
5. Xem kết quả với độ tin cậy

## Tính năng nổi bật

### Giao diện người dùng
- **Responsive**: Hoạt động tốt trên mobile và desktop
- **Modern UI**: Thiết kế hiện đại với Bootstrap 5
- **Real-time feedback**: Phản hồi ngay lập tức
- **Loading states**: Hiển thị trạng thái xử lý
- **Image preview**: Xem trước ảnh trước khi upload

### Trải nghiệm người dùng
- **Validation**: Kiểm tra định dạng và kích thước ảnh
- **Error handling**: Xử lý lỗi với thông báo rõ ràng
- **Smooth animations**: Hiệu ứng mượt mà
- **Keyboard shortcuts**: Phím tắt tiện lợi
- **Auto-dismiss alerts**: Thông báo tự động ẩn

### Hiệu suất
- **Lazy loading**: Tải ảnh theo yêu cầu
- **Debounced search**: Tìm kiếm thông minh
- **Optimized assets**: CSS/JS được tối ưu
- **Caching**: Cache hợp lý cho static files

## Cấu trúc file

```
Face/
├── server.py                 # FastAPI server chính
├── face_recognition_service.py # Service xử lý face recognition
├── requirements.txt          # Python dependencies
├── templates/               # Jinja2 templates
│   ├── base.html           # Base template
│   ├── index.html          # Trang chủ
│   ├── faces.html          # Quản lý khuôn mặt
│   ├── add_face.html       # Thêm khuôn mặt
│   ├── search.html         # Tìm kiếm
│   └── info.html           # Thông tin hệ thống
├── static/                  # Static files
│   ├── css/
│   │   └── custom.css      # CSS tùy chỉnh
│   └── js/
│       └── app.js          # JavaScript tùy chỉnh
└── images/                  # Thư mục chứa ảnh upload
```

## API Documentation

Sau khi khởi động server, truy cập:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Troubleshooting

### Lỗi thường gặp
1. **Port đã được sử dụng**: Thay đổi port trong server.py
2. **Qdrant không kết nối được**: Kiểm tra Docker container
3. **Lỗi upload ảnh**: Kiểm tra quyền ghi thư mục images/
4. **Lỗi template**: Đảm bảo thư mục templates/ tồn tại

### Performance tuning
1. **Tăng memory** cho Qdrant nếu dataset lớn
2. **Optimize ảnh** trước khi upload
3. **Sử dụng CDN** cho static files trong production
4. **Enable gzip** compression

## License

MIT License - Có thể sử dụng tự do cho mục đích cá nhân và thương mại.
