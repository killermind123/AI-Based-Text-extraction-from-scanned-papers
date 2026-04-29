from flask import Flask
from database import init_db
from routes.signup import signup_bp
from routes.dashboard import dashboard_bp
from routes.login import login_bp
from routes.logout import logout_bp
from routes.upload import upload_bp
import pytesseract
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# Initialize database
init_db()

# Configure Tesseract (Windows path — move to config file later)
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\S22247228\Downloads\tesseract.exe"

# Register blueprints
app.register_blueprint(dashboard_bp)
app.register_blueprint(signup_bp)
app.register_blueprint(login_bp)
app.register_blueprint(logout_bp)
app.register_blueprint(upload_bp)

if __name__ == "__main__":
    app.run(debug=True)