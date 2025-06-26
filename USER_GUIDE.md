# Face Recognition System - Usage Guide

## 🚀 Quick Start

### Starting the System
```bash
cd /home/linh/PycharmProjects/Face
python server.py
```

### Accessing the Web Interface
- **Main Dashboard**: http://localhost:8000
- **Face Management**: http://localhost:8000/faces/ui
- **Add New Face**: http://localhost:8000/add
- **Search Faces**: http://localhost:8000/search

## 📝 Using the System

### ➕ Adding a New Face
1. Navigate to http://localhost:8000/add
2. Fill in the required information:
   - **Tên người** (Person Name): Full name of the person
   - **Mã thẻ** (Card Code): Unique identifier/card number
   - **Chọn ảnh** (Select Image): Upload a clear face image (JPG, PNG, JPEG)
3. Click **Lưu khuôn mặt** (Save Face)
4. System will process the image and add it to the database

### 👥 Managing Faces
1. Navigate to http://localhost:8000/faces/ui
2. View all registered faces in a grid layout
3. Use the search bar to find specific people
4. Available actions for each face:
   - **👁️ View Details**: See detailed information
   - **✏️ Edit**: Modify person details or replace image
   - **🗑️ Delete**: Remove face from database

### 🔍 Searching for Faces
1. Navigate to http://localhost:8000/search
2. Upload an image to search for similar faces
3. System will return matching faces with similarity scores

## 🛠️ System Features

### Image Handling
- **Supported Formats**: JPG, JPEG, PNG
- **Auto-processing**: Face detection and embedding extraction
- **Error Handling**: Graceful fallback for missing/corrupt images
- **Static Serving**: Images served via FastAPI static files at `/images/`

### Data Structure
Each face record contains:
```json
{
    "id": "unique-uuid",
    "person_name": "Person Name",
    "image_path": "image-filename.jpg",
    "code_card": "Unique Code"
}
```

### Search & Filter
- **Text Search**: Search by name or card code
- **Sorting Options**: 
  - Name A-Z / Z-A
  - Card Code A-Z / Z-A
  - Date (Oldest/Newest)
- **Real-time Filtering**: Results update as you type

## 🔧 Technical Details

### API Endpoints
- `GET /faces` - Get all faces
- `POST /add_face` - Add new face
- `POST /search_face` - Search for similar faces
- `POST /face/edit` - Update face information
- `POST /face/delete` - Delete face

### Database
- **Vector Database**: Qdrant for face embeddings
- **Storage**: Local file system for images
- **Persistence**: Data persisted in `qdrant_data/` directory

### Requirements
- Python 3.8+
- FastAPI
- Qdrant
- OpenCV
- Face recognition libraries

## 📊 Current System Status

**✅ Fully Operational**
- 5 faces currently in database
- All CRUD operations working
- Image display functioning correctly
- Error handling implemented
- Web interface responsive and user-friendly

## 🚨 Troubleshooting

### Common Issues
1. **Images not displaying**: Check if images exist in `/images/` directory
2. **Face not detected**: Ensure image has clear, visible face
3. **Server errors**: Check console output for detailed error messages
4. **Slow performance**: Restart server if needed

### Support
- Check server logs for detailed error information
- Verify all required dependencies are installed
- Ensure Qdrant service is running properly
