from flask import Flask, render_template_string, request, jsonify
import json
import os
from threading import Thread

app = Flask('')

# Load the HTML content from an external file
current_dir = os.path.dirname(os.path.abspath(__file__))
html_file_path = os.path.join(current_dir, 'index.html')

with open(html_file_path, 'r', encoding='utf-8') as f:
    HTML_TEMPLATE = f.read()
    
def load_config():
    with open('config/config.json', 'r') as f:
        return json.load(f)

def save_config(config):
    with open('config/config.json', 'w') as f:
        json.dump(config, f, indent=4)

def get_prompt_files():
    return [f for f in os.listdir('system') if f.endswith('.txt')]

def get_prompt_contents():
    contents = {}
    for file in get_prompt_files():
        with open(os.path.join('system', file), 'r') as f:
            contents[file] = f.read()
    return contents

@app.route('/')
def home():
    config = load_config()
    prompt_files = get_prompt_files()
    prompt_contents = get_prompt_contents()
    return render_template_string(HTML_TEMPLATE, config=config, prompt_files=prompt_files, prompt_contents=prompt_contents)

@app.route('/save_config', methods=['POST'])
def save_config_endpoint():
    try:
        config = request.json
        save_config(config)
        return jsonify({'success': True, 'message': 'Configuration saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving configuration: {str(e)}'})

@app.route('/save_prompt', methods=['POST'])
def save_prompt():
    try:
        data = request.json
        filename = data['filename']
        content = data['content']

        with open(os.path.join('system', filename), 'w') as f:
            f.write(content)

        return jsonify({'success': True, 'message': 'Prompt file saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving prompt file: {str(e)}'})

@app.route('/delete_prompt', methods=['POST'])
def delete_prompt():
    try:
        filename = request.json['filename']
        if filename == 'default.txt':
            return jsonify({'success': False, 'message': 'Cannot delete default.txt'})

        os.remove(os.path.join('system', filename))
        return jsonify({'success': True, 'message': 'Prompt file deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting prompt file: {str(e)}'})

@app.route('/add_prompt', methods=['POST'])
def add_prompt():
    try:
        data = request.json
        filename = data['filename']
        content = data['content']

        if not filename.endswith('.txt'):
            filename += '.txt'

        file_path = os.path.join('system', filename)
        if os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'File already exists'})

        with open(file_path, 'w') as f:
            f.write(content)

        return jsonify({'success': True, 'message': 'Prompt file added successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error adding prompt file: {str(e)}'})

@app.route('/update_system_prompt', methods=['POST'])
def update_system_prompt():
    try:
        filename = request.json['filename']
        config = load_config()

        if not filename.startswith('system/'):
            filename = os.path.join('system', filename)
        config['system_prompt_file'] = filename

        save_config(config)
        return jsonify({'success': True, 'message': 'System prompt updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error updating system prompt: {str(e)}'})

def run():
    app.run(host='127.0.0.1', port=8080)

def config_editor():
    t = Thread(target=run)
    t.start()
    