#!/bin/bash

# Production Deployment Script for Personal RAG System
# This script handles the complete deployment pipeline

echo "🚀 Starting Personal RAG System Deployment..."

# Create data directory if it doesn't exist
mkdir -p data/documents

# Check if documents exist
if [ -z "$(ls -A data/documents 2>/dev/null)" ]; then
    echo "⚠️  No documents found in data/documents/"
    echo "📁 Please add your documents to data/documents/ and run this script again"
    exit 1
fi

echo "📁 Found documents in data/documents/:"
ls -la data/documents/

# Start the system
echo "🐳 Starting Docker containers..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check system health
echo "🔍 Checking system health..."
curl -s http://localhost:8000/health | jq '.' || echo "Backend not ready yet"

# Show logs
echo "📋 Recent backend logs:"
docker logs personal-rag-backend-1 --tail 20

echo ""
echo "🎉 Deployment complete!"
echo "🌐 Frontend: http://localhost:3000"
echo "🔧 Backend API: http://localhost:8000"
echo "📊 Qdrant: http://localhost:6333"
echo ""
echo "💡 To add new documents:"
echo "   1. Copy files to data/documents/"
echo "   2. Restart: docker-compose restart backend"
echo "   3. Or call: curl -X POST http://localhost:8000/ingest-new"
