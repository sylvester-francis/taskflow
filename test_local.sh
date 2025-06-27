#!/bin/bash

echo "🧪 Testing TaskFlow Application..."
echo "=================================="

# Test 1: Local application
echo "1. Testing local application..."
source venv/bin/activate

# Start the application in background
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
APP_PID=$!

# Wait for application to start
sleep 5

# Test endpoints
echo "  Testing health endpoint..."
if curl -f http://localhost:8000/docs > /dev/null 2>&1; then
    echo "  ✅ Application is running and healthy"
else
    echo "  ❌ Application failed to start"
    kill $APP_PID 2>/dev/null
    exit 1
fi

echo "  Testing main page..."
if curl -f http://localhost:8000/ > /dev/null 2>&1; then
    echo "  ✅ Main page accessible"
else
    echo "  ❌ Main page not accessible"
fi

echo "  Testing API registration..."
RESPONSE=$(curl -s -X POST "http://localhost:8000/api/register" \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser","email":"test@example.com","password":"testpass123"}')

if echo "$RESPONSE" | grep -q "testuser"; then
    echo "  ✅ User registration working"
else
    echo "  ❌ User registration failed"
fi

# Clean up
kill $APP_PID 2>/dev/null
echo ""
echo "🎉 Local testing complete!"
echo ""
echo "Next steps:"
echo "  1. Install Docker Desktop"
echo "  2. Run: make build"
echo "  3. Run: make run-dev"
echo "  4. Test containerized version"