"""
avry-careers Microservice Entry Point
Description: Vacancy management and applicant processing
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ensure app module is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.main import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8090"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "production") == "development"
    )
