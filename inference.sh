#!/bin/bash
# inference.sh - Script để chạy pipeline từ đầu đến cuối

echo "=========================================="
echo "VNPT AI - Inference Pipeline"
echo "=========================================="

# Kiểm tra file input
if [ ! -f "/code/private_test.json" ]; then
    echo "Error: /code/private_test.json not found!"
    exit 1
fi

echo "✓ Input file found: /code/private_test.json"

# Chạy pipeline prediction
echo "Starting prediction pipeline..."
python3 predict.py

# Kiểm tra kết quả
if [ -f "/code/submission.csv" ] && [ -f "/code/submission_time.csv" ]; then
    echo "=========================================="
    echo "✓ SUCCESS: Output files generated"
    echo "  - submission.csv"
    echo "  - submission_time.csv"
    echo "=========================================="
else
    echo "=========================================="
    echo "✗ ERROR: Output files not found!"
    echo "=========================================="
    exit 1
fi
