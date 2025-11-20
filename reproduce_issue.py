from datetime import datetime, UTC
import sys

print(f"Python version: {sys.version}")
try:
    print(f"Current time: {datetime.now(UTC)}")
    print(f"Current date: {datetime.now(UTC).date()}")
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
