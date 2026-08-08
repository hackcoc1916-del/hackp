@echo off
set GEMINI_API_KEY=your_gemini_key_here
set GROK_API_KEY=your_groq_key_here
cd /d "%~dp0backend"
echo.
echo ============================================================
echo   AEGIS Investigation Intelligence Platform
echo   Starting server on http://localhost:8000
echo ============================================================
echo.
python -m uvicorn main:app --reload --port 8000
