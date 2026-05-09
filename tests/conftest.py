import os
import sys
from unittest.mock import MagicMock

# Set dummy AWS credentials so boto3.client() at module level doesn't fail
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

# Simulate Lambda layer (/opt/python) by adding shared/ to path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "shared"))

# Mock opensearch-py so shared/opensearch.py can be imported without a real server
sys.modules.setdefault("opensearchpy", MagicMock())
