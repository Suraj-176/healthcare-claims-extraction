"""
Healthcare Claims Extraction Platform - Flask Application
Production-ready web interface with Bootstrap 5
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from flask_cors import CORS

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipeline import process_page
from cost.cost_tracker import CostTracker
from database import DatabaseManager

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

# Enable CORS
CORS(app)

# Disable browser caching - FORCE RELOAD
@app.after_request
def add_no_cache_headers(response):
    """Add headers to prevent browser caching."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# Initialize database
db = DatabaseManager()

# Allowed file extensions
ALLOWED_EXTENSIONS = {'tif', 'tiff', 'png', 'jpg', 'jpeg'} | {f'{i:03d}' for i in range(1, 100)}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================================================
# ROUTES - PAGES
# ============================================================================

@app.route('/')
def index():
    """Dashboard home page."""
    stats = db.get_stats(days=7)
    daily_stats = db.get_daily_stats(days=7)
    form_dist = db.get_form_type_distribution()
    recent_extractions = db.get_all_extractions(limit=5)
    
    return render_template('index.html', 
                         stats=stats,
                         daily_stats=daily_stats,
                         form_dist=form_dist,
                         recent=recent_extractions)


@app.route('/upload')
def upload_page():
    """Upload page."""
    return render_template('upload.html')


@app.route('/results')
def results_page():
    """Results history page."""
    # Get filter parameters
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    form_filter = request.args.get('form_type', '')
    
    # Get filtered results
    extractions = db.get_all_extractions(
        limit=50,
        status_filter=status_filter if status_filter else None,
        form_type_filter=form_filter if form_filter else None,
        search_query=search if search else None
    )
    
    # Fix provider display: extract actual provider from result_json
    for ext in extractions:
        try:
            result = json.loads(ext['result_json'])
            # Get provider from llm_escalation or use database value
            if result.get('llm_escalation', {}).get('provider'):
                ext['display_provider'] = result['llm_escalation']['provider']
            elif result.get('llm_escalation', {}).get('escalated'):
                ext['display_provider'] = 'LLM'
            elif ext['llm_provider'] and ext['llm_provider'] != 'none':
                ext['display_provider'] = ext['llm_provider']
            else:
                ext['display_provider'] = 'OCR Only'
        except:
            ext['display_provider'] = ext['llm_provider'] if ext['llm_provider'] != 'none' else 'OCR Only'
    
    return render_template('results.html', extractions=extractions)


@app.route('/settings')
def settings_page():
    """Settings page."""
    current_settings = {
        'llm_provider': db.get_setting('llm_provider') or 'auto',
        'confidence_threshold': float(db.get_setting('confidence_threshold') or '50.0'),
        'force_escalate_service_lines': db.get_setting('force_escalate_service_lines') == 'true',
        'force_escalate_revenue_lines': db.get_setting('force_escalate_revenue_lines') == 'true',
        'force_escalate_total_charge': db.get_setting('force_escalate_total_charge') == 'true',
        'show_costs': db.get_setting('show_costs') == 'true',
        'show_savings': db.get_setting('show_savings') == 'true'
    }
    
    # Check which providers are configured
    env_status = {
        'azure_openai': bool(os.getenv('AZURE_OPENAI_KEY') and os.getenv('AZURE_OPENAI_ENDPOINT')),
        'openai': bool(os.getenv('OPENAI_API_KEY')),
        'gemini': bool(os.getenv('GOOGLE_API_KEY')),
        'anthropic': bool(os.getenv('ANTHROPIC_API_KEY')),
        'groq': bool(os.getenv('GROQ_API_KEY')),
        'ollama': bool(os.getenv('OLLAMA_API_BASE'))
    }
    
    return render_template('settings.html', settings=current_settings, env_status=env_status)


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Handle file upload and processing."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not supported'}), 400
    
    try:
        # Save file with timestamp if duplicate exists
        filename = secure_filename(file.filename)
        filepath = app.config['UPLOAD_FOLDER'] / filename
        
        # Handle duplicate filenames by adding timestamp
        if filepath.exists():
            name_parts = filename.rsplit('.', 1)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if len(name_parts) == 2:
                filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
            else:
                filename = f"{filename}_{timestamp}"
            filepath = app.config['UPLOAD_FOLDER'] / filename
        
        file.save(str(filepath))
        
        # Process file
        start_time = time.time()
        tracker = CostTracker()
        result = process_page(str(filepath), tracker)
        processing_time = time.time() - start_time
        
        # Extract key info
        tier = result.get("classification", {}).get("tier", "unknown")
        status = result.get("final_status", "failed")
        mean_confidence = result.get("extraction", {}).get("mean_confidence", 0)
        cost = tracker.summary()['blended_cost_per_page']
        llm_provider = result.get("extraction", {}).get("llm_details", {}).get("provider", "none")
        
        # Save to database
        extraction_id = db.save_extraction(
            filename=filename,
            form_type=tier,
            status=status,
            mean_confidence=mean_confidence,
            cost=cost,
            processing_time=processing_time,
            llm_provider=llm_provider,
            result_json=result,
            image_path=str(filepath)
        )
        
        # Add logs
        db.add_log(extraction_id, "INFO", "upload", f"File uploaded: {filename}")
        db.add_log(extraction_id, "INFO", "processing", f"Classification: {tier}")
        db.add_log(extraction_id, "INFO", "processing", f"Status: {status}")
        
        if status == "ok":
            db.add_log(extraction_id, "INFO", "complete", f"Extraction successful (confidence: {mean_confidence:.1f}%)")
        else:
            db.add_log(extraction_id, "WARNING", "complete", f"Extraction status: {status}")
        
        # Return response
        return jsonify({
            'success': True,
            'extraction_id': extraction_id,
            'filename': filename,
            'status': status,
            'tier': tier,
            'confidence': mean_confidence,
            'cost': cost,
            'processing_time': processing_time,
            'result': result
        })
        
    except Exception as e:
        import traceback
        error_detail = str(e)
        print(f"❌ Upload error: {error_detail}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Processing failed: {error_detail}'
        }), 500


@app.route('/api/batch-upload', methods=['POST'])
def api_batch_upload():
    """Handle batch file upload and processing."""
    files = request.files.getlist('files')
    
    if not files:
        return jsonify({'error': 'No files provided'}), 400
    
    results = []
    
    for file in files:
        if file.filename == '' or not allowed_file(file.filename):
            results.append({
                'filename': file.filename,
                'status': 'skipped',
                'error': 'Invalid file type'
            })
            continue
        
        try:
            # Save and process
            filename = secure_filename(file.filename)
            filepath = app.config['UPLOAD_FOLDER'] / filename
            file.save(str(filepath))
            
            start_time = time.time()
            tracker = CostTracker()
            result = process_page(str(filepath), tracker)
            processing_time = time.time() - start_time
            
            # Extract info and save
            tier = result.get("classification", {}).get("tier", "unknown")
            status = result.get("final_status", "failed")
            mean_confidence = result.get("extraction", {}).get("mean_confidence", 0)
            cost = tracker.summary()['blended_cost_per_page']
            llm_provider = result.get("extraction", {}).get("llm_details", {}).get("provider", "none")
            
            extraction_id = db.save_extraction(
                filename=filename,
                form_type=tier,
                status=status,
                mean_confidence=mean_confidence,
                cost=cost,
                processing_time=processing_time,
                llm_provider=llm_provider,
                result_json=result,
                image_path=str(filepath)
            )
            
            results.append({
                'filename': filename,
                'status': 'success',
                'extraction_id': extraction_id,
                'tier': tier,
                'confidence': mean_confidence,
                'cost': cost,
                'processing_time': processing_time
            })
            
        except Exception as e:
            results.append({
                'filename': file.filename,
                'status': 'error',
                'error': str(e)
            })
    
    return jsonify({'results': results})


@app.route('/api/extraction/<int:extraction_id>')
def api_get_extraction(extraction_id):
    """Get single extraction details."""
    extraction = db.get_extraction_by_id(extraction_id)
    
    if not extraction:
        return jsonify({'error': 'Extraction not found'}), 404
    
    return jsonify(extraction)


@app.route('/api/extraction/<int:extraction_id>/export')
def api_export_extraction(extraction_id):
    """Export extraction as JSON file."""
    extraction = db.get_extraction_by_id(extraction_id)
    
    if not extraction:
        return jsonify({'error': 'Extraction not found'}), 404
    
    # Parse result JSON
    result = json.loads(extraction['result_json'])
    
    # Create temporary file
    export_path = app.config['UPLOAD_FOLDER'] / f"result_{extraction['filename']}.json"
    with open(export_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    return send_file(export_path, as_attachment=True, download_name=f"result_{extraction['filename']}.json")


@app.route('/api/stats')
def api_get_stats():
    """Get dashboard statistics."""
    days = request.args.get('days', 7, type=int)
    stats = db.get_stats(days=days)
    daily_stats = db.get_daily_stats(days=days)
    form_dist = db.get_form_type_distribution()
    
    return jsonify({
        'stats': stats,
        'daily_stats': daily_stats,
        'form_distribution': form_dist
    })


@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    """Save settings."""
    data = request.json
    
    try:
        for key, value in data.items():
            db.set_setting(key, str(value).lower() if isinstance(value, bool) else str(value))
        
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/extraction/<int:extraction_id>', methods=['DELETE'])
def api_delete_extraction(extraction_id):
    """Delete extraction."""
    try:
        db.delete_extraction(extraction_id)
        return jsonify({'success': True, 'message': 'Extraction deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
