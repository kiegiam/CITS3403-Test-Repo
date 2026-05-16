import sys
import os

# Ensure the project root is always on the Python path when running pytest
# from any directory, so `from app import ...` works inside tests/
sys.path.insert(0, os.path.dirname(__file__))
