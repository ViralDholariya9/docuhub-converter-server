import os
import subprocess
import tempfile
from flask import Flask, request, send_file, jsonify

app = Flask(__name__)

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'DocuHub Conversion Server is running!'
    })

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({'error': 'No filename'}), 400

    file_ext = os.path.splitext(uploaded_file.filename)[1].lower()
    if file_ext not in ['.docx', '.doc', '.xlsx', '.xls', '.pdf']:
        return jsonify({'error': f'Unsupported file format: {file_ext}'}), 400

    to_format = 'pdf'
    if file_ext == '.pdf':
        to_format = 'docx'

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = os.path.join(temp_dir, uploaded_file.filename)
        uploaded_file.save(input_path)

        cmd = [
            'libreoffice',
            '--headless',
            '--convert-to', to_format,
            '--outdir', temp_dir,
            input_path
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if result.returncode != 0:
                return jsonify({
                    'error': 'LibreOffice conversion failed',
                    'details': result.stderr.decode('utf-8')
                }), 500

            base_name = os.path.splitext(uploaded_file.filename)[0]
            output_file_name = f"{base_name}.{to_format}"
            output_path = os.path.join(temp_dir, output_file_name)

            if os.path.exists(output_path):
                return send_file(
                    output_path,
                    mimetype='application/octet-stream',
                    as_attachment=True,
                    download_name=output_file_name
                )
            else:
                for file in os.listdir(temp_dir):
                    if file.endswith(f".{to_format}"):
                        return send_file(
                            os.path.join(temp_dir, file),
                            mimetype='application/octet-stream',
                            as_attachment=True,
                            download_name=file
                        )
                return jsonify({'error': 'Converted file not found'}), 500

        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Conversion process timed out'}), 504
        except Exception as e:
            return jsonify({'error': f'Server error during conversion: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
