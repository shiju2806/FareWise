#!/usr/bin/env bash
# End-to-end test script for Smart Single-Extract Chat Architecture
# Tests the /api/trips/chat endpoint against a running backend (port 8080)

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2N2Y0YWY5Ny1iNjM2LTQ5NzktOGM4My1hOGQ3NTdjOTI2MDAifQ.WQg1x74sZzjzZjEFbATpojx1Puhn2tbd1B4uWtrC9OQ"
BASE_URL="http://localhost:8080/api/trips/chat"
TMPDIR=$(mktemp -d)
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

chat_to_file() {
  local outfile="$1"
  local message="$2"
  local partial_file="${3:-}"
  local history_file="${4:-}"

  local partial="null"
  local history="[]"
  [ -n "$partial_file" ] && [ -f "$partial_file" ] && partial=$(cat "$partial_file")
  [ -n "$history_file" ] && [ -f "$history_file" ] && history=$(cat "$history_file")

  python3 -c "
import json, sys
payload = {
    'message': sys.argv[1],
    'conversation_history': json.loads(sys.argv[2]),
    'partial_trip': json.loads(sys.argv[3])
}
print(json.dumps(payload))
" "$message" "$history" "$partial" > "$TMPDIR/payload.json"

  curl -s -X POST "$BASE_URL" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d @"$TMPDIR/payload.json" > "$outfile"
}

check() {
  local label="$1" file="$2" expr="$3" expected="$4"
  local actual
  actual=$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print($expr)
" "$file" 2>/dev/null) || actual="ERROR"

  if [ "$actual" = "$expected" ]; then
    echo -e "  ${GREEN}PASS${NC} $label = $actual"
    ((PASS++)) || true
  else
    echo -e "  ${RED}FAIL${NC} $label: expected '$expected', got '$actual'"
    ((FAIL++)) || true
  fi
}

check_contains() {
  local label="$1" file="$2" expr="$3" needle="$4"
  local actual
  actual=$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print($expr)
" "$file" 2>/dev/null) || actual=""

  if echo "$actual" | grep -qi "$needle"; then
    echo -e "  ${GREEN}PASS${NC} $label: contains '$needle'"
    ((PASS++)) || true
  else
    echo -e "  ${RED}FAIL${NC} $label: missing '$needle'"
    ((FAIL++)) || true
  fi
}

extract_to_file() {
  local infile="$1" outfile="$2" expr="$3"
  python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print($expr)
" "$infile" > "$outfile"
}

echo ""
echo "=========================================="
echo " Smart Chat Architecture — E2E Tests"
echo "=========================================="
echo ""

# ------------------------------------------------------------------
# TEST 1: Full info in one message
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 1: Full info in one message${NC}"
echo "  Input: 'Toronto to London mid April business Air Canada with my wife'"
chat_to_file "$TMPDIR/t1.json" "Toronto to London mid April business Air Canada with my wife"

check "trip_ready"       "$TMPDIR/t1.json" "d['trip_ready']" "True"
check "stage"            "$TMPDIR/t1.json" "d['partial_trip']['_agent_state']['stage']" "ready"
check "companions_count" "$TMPDIR/t1.json" "d['partial_trip']['_agent_state']['companions_count']" "1"
check "companions_asked" "$TMPDIR/t1.json" "d['partial_trip']['_agent_state']['companions_asked']" "True"
check "budget_calc"      "$TMPDIR/t1.json" "d['partial_trip']['_agent_state']['companions_budget_calculated']" "True"
check "has flight_card"  "$TMPDIR/t1.json" "'flight_card' in [b['type'] for b in d.get('blocks',[])]" "True"
check "has budget_card"  "$TMPDIR/t1.json" "'budget_card' in [b['type'] for b in d.get('blocks',[])]" "True"
check "no companion_prompt" "$TMPDIR/t1.json" "'companion_prompt' in [b['type'] for b in d.get('blocks',[])]" "False"
check "state_version"    "$TMPDIR/t1.json" "d['partial_trip']['_agent_state']['_version']" "3"
echo ""

# ------------------------------------------------------------------
# TEST 2: Business without companions — asks after search
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 2: Business without companion info${NC}"
echo "  Input: 'Toronto to London mid April business round'"
chat_to_file "$TMPDIR/t2.json" "Toronto to London mid April business round"

check "trip_ready"       "$TMPDIR/t2.json" "d['trip_ready']" "False"
check "companions_count" "$TMPDIR/t2.json" "d['partial_trip']['_agent_state']['companions_count']" "-1"
check "companions_asked" "$TMPDIR/t2.json" "d['partial_trip']['_agent_state']['companions_asked']" "True"
check "has flight_card"  "$TMPDIR/t2.json" "'flight_card' in [b['type'] for b in d.get('blocks',[])]" "True"
check "has companion_prompt" "$TMPDIR/t2.json" "'companion_prompt' in [b['type'] for b in d.get('blocks',[])]" "True"
check "no budget_card"   "$TMPDIR/t2.json" "'budget_card' in [b['type'] for b in d.get('blocks',[])]" "False"
check_contains "reply mentions solo/family" "$TMPDIR/t2.json" "d['reply']" "solo"
echo ""

# ------------------------------------------------------------------
# TEST 3: Follow-up — "just me" completes trip
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 3: Solo response completes trip${NC}"
echo "  Input: 'just me' (continuing from Test 2)"

extract_to_file "$TMPDIR/t2.json" "$TMPDIR/t2_partial.json" "json.dumps(d['partial_trip'])"
extract_to_file "$TMPDIR/t2.json" "$TMPDIR/t2_history.json" "json.dumps(d['conversation_history'])"
chat_to_file "$TMPDIR/t3.json" "just me" "$TMPDIR/t2_partial.json" "$TMPDIR/t2_history.json"

check "trip_ready"       "$TMPDIR/t3.json" "d['trip_ready']" "True"
check "companions_count" "$TMPDIR/t3.json" "d['partial_trip']['_agent_state']['companions_count']" "0"
check "stage"            "$TMPDIR/t3.json" "d['partial_trip']['_agent_state']['stage']" "ready"
echo ""

# ------------------------------------------------------------------
# TEST 4: Economy trip — ready immediately
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 4: Economy trip — immediate ready${NC}"
echo "  Input: 'Toronto to NYC Friday'"
chat_to_file "$TMPDIR/t4.json" "Toronto to NYC Friday"

check "trip_ready"       "$TMPDIR/t4.json" "d['trip_ready']" "True"
check "no flight_card"   "$TMPDIR/t4.json" "'flight_card' in [b['type'] for b in d.get('blocks',[])]" "False"
check "no companion_prompt" "$TMPDIR/t4.json" "'companion_prompt' in [b['type'] for b in d.get('blocks',[])]" "False"
echo ""

# ------------------------------------------------------------------
# TEST 5: Business with wife and 2 kids
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 5: Business with wife and 2 kids${NC}"
echo "  Input: 'Toronto to London mid April business with my wife and 2 kids'"
chat_to_file "$TMPDIR/t5.json" "Toronto to London mid April business with my wife and 2 kids"

check "trip_ready"       "$TMPDIR/t5.json" "d['trip_ready']" "True"
check "companions_count" "$TMPDIR/t5.json" "d['partial_trip']['_agent_state']['companions_count']" "3"
check "budget_calc"      "$TMPDIR/t5.json" "d['partial_trip']['_agent_state']['companions_budget_calculated']" "True"
check "has flight_card"  "$TMPDIR/t5.json" "'flight_card' in [b['type'] for b in d.get('blocks',[])]" "True"
check "has budget_card"  "$TMPDIR/t5.json" "'budget_card' in [b['type'] for b in d.get('blocks',[])]" "True"
echo ""

# ------------------------------------------------------------------
# TEST 6: Business solo explicit
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 6: Business solo explicit${NC}"
echo "  Input: 'Toronto to London mid April business just me'"
chat_to_file "$TMPDIR/t6.json" "Toronto to London mid April business just me"

check "trip_ready"       "$TMPDIR/t6.json" "d['trip_ready']" "True"
check "companions_count" "$TMPDIR/t6.json" "d['partial_trip']['_agent_state']['companions_count']" "0"
check "has flight_card"  "$TMPDIR/t6.json" "'flight_card' in [b['type'] for b in d.get('blocks',[])]" "True"
check "no budget_card"   "$TMPDIR/t6.json" "'budget_card' in [b['type'] for b in d.get('blocks',[])]" "False"
check "no companion_prompt" "$TMPDIR/t6.json" "'companion_prompt' in [b['type'] for b in d.get('blocks',[])]" "False"
echo ""

# ------------------------------------------------------------------
# TEST 7: Partial info — missing origin
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 7: Partial info — missing origin${NC}"
echo "  Input: 'London business'"
chat_to_file "$TMPDIR/t7.json" "London business"

check "trip_ready"       "$TMPDIR/t7.json" "d['trip_ready']" "False"
check "no flight_card"   "$TMPDIR/t7.json" "'flight_card' in [b['type'] for b in d.get('blocks',[])]" "False"
echo ""

# ------------------------------------------------------------------
# TEST 8: Follow-up with companion count after prompt
# ------------------------------------------------------------------
echo -e "${YELLOW}TEST 8: wife and 2 kids after companion prompt${NC}"
echo "  Input: 'wife and 2 kids' (continuing from Test 2)"
chat_to_file "$TMPDIR/t8.json" "wife and 2 kids" "$TMPDIR/t2_partial.json" "$TMPDIR/t2_history.json"

check "trip_ready"       "$TMPDIR/t8.json" "d['trip_ready']" "True"
check "companions_count" "$TMPDIR/t8.json" "d['partial_trip']['_agent_state']['companions_count']" "3"
check "budget_calc"      "$TMPDIR/t8.json" "d['partial_trip']['_agent_state']['companions_budget_calculated']" "True"
check "has budget_card"  "$TMPDIR/t8.json" "'budget_card' in [b['type'] for b in d.get('blocks',[])]" "True"
echo ""

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
TOTAL=$((PASS + FAIL))
echo "=========================================="
if [ "$FAIL" -eq 0 ]; then
  echo -e " ${GREEN}ALL $TOTAL TESTS PASSED${NC}"
else
  echo -e " ${RED}$FAIL FAILED${NC} / $TOTAL total ($PASS passed)"
fi
echo "=========================================="
echo ""

rm -rf "$TMPDIR"
exit "$FAIL"
