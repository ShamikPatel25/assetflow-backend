import os
import re

project_dir = "/home/shamik/Projects/assetflow-backend"
ignore_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", "htmlcov", "media", "staticfiles"}

folders = []
files_data = []
endpoints = []
models = []
jobs = []
integrations = []

total_files = 0
skipped_files = []

def get_language(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.py': return 'Python'
    if ext == '.html': return 'HTML'
    if ext == '.css': return 'CSS'
    if ext == '.js': return 'JavaScript'
    if ext == '.md': return 'Markdown'
    if ext == '.sh': return 'Shell'
    if ext == '.json': return 'JSON'
    return 'Text'

for root, dirs, files in os.walk(project_dir):
    dirs[:] = [d for d in dirs if d not in ignore_dirs]
    rel_root = os.path.relpath(root, project_dir)
    if rel_root != '.':
        folders.append(rel_root)
    
    for f in files:
        if f.endswith('.pyc') or f.endswith('.pyo'):
            continue
            
        filepath = os.path.join(root, f)
        rel_path = os.path.relpath(filepath, project_dir)
        total_files += 1
        
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                line_count = len(lines)
                
                # Check for models
                for i, line in enumerate(lines):
                    if re.match(r'^class \w+\(models\.Model\):', line) or re.match(r'^class \w+\(TenantMixin\):', line) or re.match(r'^class \w+\(AbstractUser\):', line):
                        models.append(f"{rel_path}:{i+1} | {line.strip()}")
                        
                    # Check for urls/endpoints
                    if 'path(' in line and 'name=' in line:
                        endpoints.append(f"{rel_path}:{i+1} | {line.strip()}")
                        
                    # Check for jobs/commands
                    if 'BaseCommand' in line or '@shared_task' in line or '@app.task' in line:
                        jobs.append(f"{rel_path}:{i+1} | {line.strip()}")
                        
                    # Check for integrations
                    lower_line = line.lower()
                    if any(x in lower_line for x in ['stripe', 'twilio', 'aws', 's3', 'boto3', 'sendgrid', 'openai', 'gemini', 'anthropic']):
                        integrations.append(f"{rel_path}:{i+1} | {line.strip()}")
                        
                files_data.append(f"{rel_path} | {get_language(f)} | {line_count} | Not read (parsed via script)")
                
        except Exception as e:
            skipped_files.append(rel_path)

with open("/home/shamik/.gemini/antigravity/brain/0e573935-ced6-4506-8b8e-c4cc11ccea88/inventory_report.md", "w") as out:
    out.write("# Project Inventory\n\n")
    
    out.write("## 1. Folders\n| Folder | Purpose Guess |\n|---|---|\n")
    for d in sorted(folders):
        out.write(f"| {d} | Unconfirmed |\n")
        
    out.write("\n## 2. Files\n| File Path | Language | Lines | Purpose |\n|---|---|---|---|\n")
    for fd in sorted(files_data):
        out.write(f"| {fd} |\n")
        
    out.write("\n## 3. API Endpoints\n| Source | Endpoint Definition |\n|---|---|\n")
    for ep in endpoints:
        out.write(f"| {ep} |\n")
        
    out.write("\n## 4. Database Models\n| Source | Model Definition |\n|---|---|\n")
    for m in models:
        out.write(f"| {m} |\n")
        
    out.write("\n## 5. Background Jobs & Scheduled Tasks\n| Source | Task Definition |\n|---|---|\n")
    for j in jobs:
        out.write(f"| {j} |\n")
        
    out.write("\n## 6. Third-Party Integrations\n| Source | Integration Reference |\n|---|---|\n")
    for ind in integrations:
        out.write(f"| {ind} |\n")
        
    out.write(f"\n## 7. Summary\nTotal files scanned: {total_files}. Files skipped or not read: {len(skipped_files)} ({', '.join(skipped_files) if skipped_files else 'None'}).\n")
