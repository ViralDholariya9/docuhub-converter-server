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

    # If it is a PDF, convert it to DOCX using pdf2docx
    if file_ext == '.pdf':
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, uploaded_file.filename)
            uploaded_file.save(input_path)

            base_name = os.path.splitext(uploaded_file.filename)[0]
            output_file_name = f"{base_name}.docx"
            output_path = os.path.join(temp_dir, output_file_name)

            try:
                from pdf2docx import Converter
                cv = Converter(input_path)
                # Disable table parsing to prevent Out of Memory (OOM) on free 512MB RAM hosting
                cv.convert(output_path, start=0, end=None, parse_table=False)
                cv.close()

                if os.path.exists(output_path):
                    return send_file(
                        output_path,
                        mimetype='application/octet-stream',
                        as_attachment=True,
                        download_name=output_file_name
                    )
                else:
                    return jsonify({'error': 'Converted DOCX file not found'}), 500
            except Exception as e:
                return jsonify({'error': f'PDF to Word conversion failed: {str(e)}'}), 500

    # Otherwise, it's Office to PDF (using LibreOffice)
    to_format = 'pdf'
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

import re
import urllib.request
from urllib.parse import urljoin

def make_links_absolute(html, base_url):
    def replacer(match):
        attr = match.group(1)
        url = match.group(2)
        if url.startswith('http://') or url.startswith('https://') or url.startswith('data:'):
            return match.group(0)
        absolute_url = urljoin(base_url, url)
        return f'{attr}="{absolute_url}"'

    pattern = re.compile(r'(src|href)=["\']([^"\']*)["\']', re.IGNORECASE)
    return pattern.sub(replacer, html)

@app.route('/html-to-pdf', methods=['POST'])
def html_to_pdf():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Missing URL'}), 400

    url = data['url']
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return jsonify({'error': f'Failed to fetch URL: {str(e)}'}), 400

    try:
        html_content = make_links_absolute(html_content, url)
    except Exception:
        pass

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = os.path.join(temp_dir, 'webpage.html')
        with open(input_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        cmd = [
            'libreoffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', temp_dir,
            input_path
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            if result.returncode != 0:
                return jsonify({
                    'error': 'LibreOffice conversion failed',
                    'details': result.stderr.decode('utf-8', errors='ignore')
                }), 500

            output_path = os.path.join(temp_dir, 'webpage.pdf')
            if os.path.exists(output_path):
                return send_file(
                    output_path,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name='webpage.pdf'
                )
            else:
                return jsonify({'error': 'PDF file not generated'}), 500
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Conversion process timed out'}), 504
        except Exception as e:
            return jsonify({'error': f'Error during conversion: {str(e)}'}), 500

@app.route('/encrypt-excel', methods=['POST'])
def encrypt_excel():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    if 'password' not in request.form:
        return jsonify({'error': 'Password is required'}), 400

    uploaded_file = request.files['file']
    password = request.form['password']

    if uploaded_file.filename == '':
        return jsonify({'error': 'No filename'}), 400

    import msoffcrypto
    from msoffcrypto.format.ooxml import OOXMLFile

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = os.path.join(temp_dir, uploaded_file.filename)
        uploaded_file.save(input_path)

        output_file_name = f"Encrypted_{uploaded_file.filename}"
        output_path = os.path.join(temp_dir, output_file_name)

        try:
            with open(input_path, "rb") as f_in:
                file = OOXMLFile(f_in)
                with open(output_path, "wb") as f_out:
                    file.encrypt(password, f_out)

            if os.path.exists(output_path):
                return send_file(
                    output_path,
                    mimetype='application/octet-stream',
                    as_attachment=True,
                    download_name=output_file_name
                )
            else:
                return jsonify({'error': 'Encrypted file not generated'}), 500
        except Exception as e:
            return jsonify({'error': f'Excel encryption failed: {str(e)}'}), 500

@app.route('/decrypt-excel', methods=['POST'])
def decrypt_excel():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    if 'password' not in request.form:
        return jsonify({'error': 'Password is required'}), 400

    uploaded_file = request.files['file']
    password = request.form['password']

    if uploaded_file.filename == '':
        return jsonify({'error': 'No filename'}), 400

    import msoffcrypto

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = os.path.join(temp_dir, uploaded_file.filename)
        uploaded_file.save(input_path)

        output_file_name = f"Decrypted_{uploaded_file.filename}"
        output_path = os.path.join(temp_dir, output_file_name)

        try:
            with open(input_path, "rb") as f_in:
                file = msoffcrypto.OfficeFile(f_in)
                file.load_key(password=password)
                with open(output_path, "wb") as f_out:
                    file.decrypt(f_out)

            if os.path.exists(output_path):
                return send_file(
                    output_path,
                    mimetype='application/octet-stream',
                    as_attachment=True,
                    download_name=output_file_name
                )
            else:
                return jsonify({'error': 'Decrypted file not generated'}), 500
        except Exception as e:
            return jsonify({'error': f'Excel decryption failed (please check password): {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
