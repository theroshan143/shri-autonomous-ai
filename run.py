"""
Entry point — run with `python run.py` or `uvicorn app.main:app`.
"""

# pyrefly: ignore [missing-import]
import uvicorn
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()  # Load .env file if present

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # reload off for production/demo stability
    )
