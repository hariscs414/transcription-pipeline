#!/usr/bin/env bash
# End-to-end manual test for the transcription API.
# Run this AFTER starting the server: uvicorn app.main:app --reload
#
# Usage: ./tests/manual_test.sh [path/to/audio.wav]

set -e

AUDIO_FILE="${1:-samples/sample.wav}"
BASE_URL="http://localhost:8000"

echo "1) Health check"
curl -s "$BASE_URL/health"
echo -e "\n"

echo "2) Uploading $AUDIO_FILE"
RESPONSE=$(curl -s -F "file=@${AUDIO_FILE}" "$BASE_URL/transcribe")
echo "$RESPONSE"
JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID: $JOB_ID"
echo ""

echo "3) Polling for result (every 2s, up to 60s)"
for i in $(seq 1 30); do
  RESULT=$(curl -s "$BASE_URL/transcription/$JOB_ID")
  STATUS=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
  echo "  [$i] status: $STATUS"
  if [ "$STATUS" = "done" ] || [ "$STATUS" = "failed" ]; then
    echo ""
    echo "Final result:"
    echo "$RESULT" | python3 -m json.tool
    break
  fi
  sleep 2
done

echo ""
echo "4) Testing unsupported format (expect 400)"
echo "not audio" > /tmp/fake.txt
curl -s -F "file=@/tmp/fake.txt" "$BASE_URL/transcribe"
echo ""

echo ""
echo "5) Testing 404 for unknown job"
curl -s "$BASE_URL/transcription/does-not-exist"
echo ""
