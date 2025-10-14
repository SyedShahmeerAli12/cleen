@echo off
REM Production Deployment Script for Personal RAG System (Windows)
REM This script handles the complete deployment pipeline

echo 🚀 Starting Personal RAG System Deployment...

REM Create data directory if it doesn't exist
if not exist "data\documents" mkdir "data\documents"

REM Check if documents exist
dir "data\documents\*.txt" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  No documents found in data\documents\
    echo 📁 Please add your documents to data\documents\ and run this script again
    pause
    exit /b 1
)

echo 📁 Found documents in data\documents\:
dir "data\documents\"

REM Start the system
echo 🐳 Starting Docker containers...
docker-compose up -d

REM Wait for services to be ready
echo ⏳ Waiting for services to start...
timeout /t 10 /nobreak >nul

REM Check system health
echo 🔍 Checking system health...
powershell -Command "try { Invoke-RestMethod -Uri 'http://localhost:8000/health' -Method GET } catch { Write-Host 'Backend not ready yet' }"

REM Show logs
echo 📋 Recent backend logs:
docker logs personal-rag-backend-1 --tail 20

echo.
echo 🎉 Deployment complete!
echo 🌐 Frontend: http://localhost:3000
echo 🔧 Backend API: http://localhost:8000
echo 📊 Qdrant: http://localhost:6333
echo.
echo 💡 To add new documents:
echo    1. Copy files to data\documents\
echo    2. Restart: docker-compose restart backend
echo    3. Or call: Invoke-RestMethod -Uri "http://localhost:8000/ingest-new" -Method POST

pause
