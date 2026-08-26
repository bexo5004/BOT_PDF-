"""
api.py - API لمعالجة الملفات عبر HTTP
"""

import os
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from config import Config
from file_engine import FileEngine
from utils import logger, safe_remove, format_size

app = Flask(__name__)
CORS(app)

# إعدادات
UPLOAD_FOLDER = Config.TEMP_DIR
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 جيجابايت
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

API_TOKEN = os.getenv("API_TOKEN", "HATEMPDFBEXO")

def check_token():
    token = request.headers.get('X-API-Token')
    return token == API_TOKEN

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'max_file_size': format_size(MAX_FILE_SIZE)
    }), 200

@app.route('/convert-to-pdf', methods=['POST'])
def convert_to_pdf():
    if not check_token():
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        filename = secure_filename(file.filename)
        file_path = Path(UPLOAD_FOLDER) / f"api_{os.urandom(4).hex()}_{filename}"
        file.save(str(file_path))
        
        pdf_path = FileEngine.convert_to_pdf(str(file_path))
        
        if str(file_path) != pdf_path:
            safe_remove(str(file_path))
        
        return jsonify({
            'status': 'success',
            'filename': Path(pdf_path).name,
            'download_url': f"/download/{Path(pdf_path).name}"
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/merge', methods=['POST'])
def merge_files():
    if not check_token():
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files selected'}), 400
    
    try:
        file_paths = []
        for file in files:
            filename = secure_filename(file.filename)
            file_path = Path(UPLOAD_FOLDER) / f"api_{os.urandom(4).hex()}_{filename}"
            file.save(str(file_path))
            file_paths.append(str(file_path))
        
        result_path = FileEngine.merge_documents(file_paths)
        
        for path in file_paths:
            safe_remove(path)
        
        return jsonify({
            'status': 'success',
            'filename': Path(result_path).name,
            'download_url': f"/download/{Path(result_path).name}"
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/compress', methods=['POST'])
def compress_pdf():
    if not check_token():
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        filename = secure_filename(file.filename)
        file_path = Path(UPLOAD_FOLDER) / f"api_{os.urandom(4).hex()}_{filename}"
        file.save(str(file_path))
        
        result_path, before, after = FileEngine.compress_pdf(str(file_path))
        
        if str(file_path) != result_path:
            safe_remove(str(file_path))
        
        return jsonify({
            'status': 'success',
            'before': before,
            'after': after,
            'filename': Path(result_path).name,
            'download_url': f"/download/{Path(result_path).name}"
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/extract-images', methods=['POST'])
def extract_images():
    if not check_token():
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        filename = secure_filename(file.filename)
        file_path = Path(UPLOAD_FOLDER) / f"api_{os.urandom(4).hex()}_{filename}"
        file.save(str(file_path))
        
        img_data, img_filename = FileEngine.extract_images_from_pdf(str(file_path))
        
        output_path = Path(UPLOAD_FOLDER) / f"extracted_{os.urandom(4).hex()}_{img_filename}"
        with open(output_path, 'wb') as f:
            f.write(img_data)
        
        safe_remove(str(file_path))
        
        return jsonify({
            'status': 'success',
            'filename': img_filename,
            'download_url': f"/download/{Path(output_path).name}"
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    file_path = Path(UPLOAD_FOLDER) / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    logger.info("🚀 API يعمل على المنفذ 5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
