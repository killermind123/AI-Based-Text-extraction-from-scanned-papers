from flask import Flask
from database import init_db
from routes.signup import signup_bp
from routes.dashboard import dashboard_bp
from routes.login import login_bp
from routes.logout import logout_bp
from routes.upload import upload_bp
from routes.profile import profile_bp
from routes.home import home_bp
from routes.runsheet import runsheet_bp
import pytesseract
import shutil
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# Initialize database
init_db()

# Auto-detect Tesseract — works on any machine
tesseract_path = shutil.which("tesseract")

if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    print(f"Tesseract found in PATH: {tesseract_path}")
else:
    common_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\S22247228\Downloads\tesseract.exe",
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
    ]
    for path in common_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            print(f"Tesseract found at: {path}")
            break
    else:
        print("WARNING: Tesseract not found. OCR will not work.")

# Register blueprints
app.register_blueprint(dashboard_bp)
app.register_blueprint(home_bp)
app.register_blueprint(signup_bp)
app.register_blueprint(login_bp)
app.register_blueprint(logout_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(runsheet_bp)

if __name__ == "__main__":
    app.run(debug=True)