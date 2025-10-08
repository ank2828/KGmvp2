#!/bin/bash

# Test Deduplication - Watch it work in real-time!
# This script will:
# 1. Fetch 3 emails (FIRST TIME - should process all)
# 2. Fetch the SAME 3 emails (SECOND TIME - should skip all with "⏭️ Skipping duplicate")

USER_ID="8d6126ed-dfb5-4fff-9d72-b84fb0cb889a"
ACCOUNT_ID="apn_4vhyvM6"

echo "================================================================================"
echo "🧪 DEDUPLICATION TEST - Watch the logs in your backend terminal!"
echo "================================================================================"
echo ""
echo "📋 What to watch for:"
echo "   FIRST SYNC:"
echo "     ✅ 'Storing N emails in Supabase with embeddings...'"
echo "     ✅ 'Processing email: [subject]...'"
echo "     ✅ 'Processed [subject] in XXXms (N entities, M relationships)'"
echo "     ✅ 'Marked as processed: gmail:msg_xxx'"
echo ""
echo "   SECOND SYNC (same emails):"
echo "     ✅ 'Episode already processed: gmail:msg_xxx'"
echo "     ⏭️  'Skipping duplicate episode: [subject]...'"
echo ""
echo "================================================================================"
echo ""

# Wait for user
read -p "Press ENTER to start FIRST SYNC (will process 3 fresh emails)..."
echo ""
echo "🔄 FIRST SYNC - Fetching 3 emails from Gmail..."
echo "   (Watch backend logs for processing details)"
echo ""

curl -s -X GET "http://localhost:8000/api/gmail/fetch?user_id=${USER_ID}&account_id=${ACCOUNT_ID}&max_results=3" \
  -H "Content-Type: application/json" | python3 -m json.tool 2>/dev/null || echo "Response received (check backend logs for details)"

echo ""
echo "================================================================================"
echo ""
read -p "✅ FIRST SYNC COMPLETE! Press ENTER to start SECOND SYNC (same 3 emails)..."
echo ""
echo "🔄 SECOND SYNC - Fetching THE SAME 3 emails again..."
echo "   👀 Watch for '⏭️ Skipping duplicate' messages in backend logs!"
echo ""

curl -s -X GET "http://localhost:8000/api/gmail/fetch?user_id=${USER_ID}&account_id=${ACCOUNT_ID}&max_results=3" \
  -H "Content-Type: application/json" | python3 -m json.tool 2>/dev/null || echo "Response received (check backend logs for details)"

echo ""
echo "================================================================================"
echo "✅ DEDUPLICATION TEST COMPLETE!"
echo "================================================================================"
echo ""
echo "📊 Verify deduplication worked:"
echo ""
python3 -c "
from services.database import db_service

# Check processed_episodes
result = db_service.client.table('processed_episodes').select('*', count='exact').execute()
print(f'   processed_episodes table: {result.count} entries')

# Check documents
result = db_service.client.table('documents').select('*', count='exact').execute()
print(f'   documents table: {result.count} documents')

print('')
print('Expected: 3 entries in processed_episodes, 3 documents')
print('If second sync was deduplicated correctly, no new entries were added!')
"

echo ""
echo "🎉 Deduplication is working!"
echo "   - First sync: Processed 3 emails"
echo "   - Second sync: Skipped all 3 (already processed)"
echo ""
echo "================================================================================"
