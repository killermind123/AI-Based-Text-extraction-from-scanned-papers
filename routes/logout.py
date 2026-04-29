from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import init_db, get_connection
import pytesseract
from PIL import Image
import os
import re

logout_bp = Blueprint("logout", __name__)

@logout_bp.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")
