"""
Test suite for the lisztserv package.
"""

import os
import sys
from pathlib import Path

# Add the src directory to Python path for test imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src')) 