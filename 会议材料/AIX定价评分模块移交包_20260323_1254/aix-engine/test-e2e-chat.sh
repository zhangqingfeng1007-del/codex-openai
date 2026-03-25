#!/usr/bin/env bash
# AIX 保险智能体 — 全链路 E2E 冒烟测试
# 用法：bash test-e2e-chat.sh [base_url]
#
# SSE 格式说明：每个事件两行
#   event: <type>
#   data: <json>
# grep "^data:" 只抓数据行，所以检测事件类型要用 grep "^event:" 或捕获全部输出

BASE=${1:-http://localhost}
PASS=0; FAIL=0

echo "================================================"
echo "  AIX E2E Smoke Test — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Target: $BASE"
echo "================================================"

check() {
  local label="$1" result="$2" expect="$3"
  if echo "$result" | grep -q "$expect"; then
    echo "  ✅ $label"
    PASS=$((PASS+1))
  else
    echo "  ❌ $label (expected: $expect)"
    FAIL=$((FAIL+1))
  fi
}

# 捕获完整 SSE 输出（包含 event: 和 data: 行）
run_sse() {
  local label="$1" payload="$2" timeout="${3:-45}"
  echo ""
  echo "─── [$label] ───────────────────────────────────"
  curl -s --max-time "$timeout" \
    -X POST "$BASE/api/v1/chat" \
    -H "Content-Type: application/json" \
    -d "$payload" --no-buffer || true
}

# ── Case 0: 健康检查 ─────────────────────────────────
echo ""
echo "─── [health] ───────────────────────────────────"
HEALTH=$(curl -s --max-time 5 "$BASE/health" 2>&1 || echo "UNREACHABLE")
if echo "$HEALTH" | grep -qi "ok\|healthy\|running"; then
  echo "  ✅ health OK"
  PASS=$((PASS+1))
else
  echo "  ⚠️  /health 无标准响应（继续测试）"
fi

# ── Case 1: 问候 ─────────────────────────────────────
OUT1=$(run_sse "greeting" '{"messages":[{"role":"user","content":"你好"}]}' 30)
echo "$OUT1" | grep "^event:\|^data:" | head -20
# SSE event: chunk 在 "event:" 行，data 在 "data:" 行
check "greeting: chunk event"    "$OUT1" '^event: chunk'
check "greeting: done event"     "$OUT1" '^event: done'
check "greeting: no error event" "$(echo "$OUT1" | grep -v '^event: error' || true)" "."

# ── Case 2: 规划意图 → route_options ─────────────────
OUT2=$(run_sse "route_options" '{"messages":[{"role":"user","content":"帮我做一个家庭保险规划，我不知道从哪里开始"}]}' 45)
echo "$OUT2" | grep "^event:\|^data:" | head -20
check "route_options: event exists"   "$OUT2" '^event: route_options'
check "route_options: has label"      "$OUT2" '"label"'
check "route_options: has aix-engine" "$OUT2" 'aix-engine'
check "route_options: no error"       "$(echo "$OUT2" | grep -v '^event: error' || true)" "."

# ── Case 3: 完整需求 → needs_report + product_recommendations
FULL='{"messages":[{"role":"user","content":"我35岁男性，在北京工作，月收入2万，有妻子和一个5岁孩子，想买重疾险，预算8000元每年，帮我推荐最适合的产品"}]}'
OUT3=$(run_sse "full_needs" "$FULL" 90)
echo "$OUT3" | grep "^event:\|^data:" | head -10

check "full_needs: needs_report event"            "$OUT3" '^event: needs_report'
check "full_needs: age in summary"                "$OUT3" '"age"'
check "full_needs: budget_mode in summary"        "$OUT3" '"budget_mode"'
check "full_needs: product_recommendations event" "$OUT3" '^event: product_recommendations'
check "full_needs: top3 exists"                   "$OUT3" '"top3"'
check "full_needs: product_name exists"           "$OUT3" '"product_name"'
check "full_needs: total_score > 0"               "$OUT3" '"total_score": [1-9]'
check "full_needs: conclusion exists"             "$OUT3" '"conclusion"'
check "full_needs: risk_notes exists"             "$OUT3" '"risk_notes"'
check "full_needs: budget_allocation exists"      "$OUT3" '"budget_allocation"'
check "full_needs: by_person exists"              "$OUT3" '"by_person"'
check "full_needs: no error event"                "$(echo "$OUT3" | grep -v '^event: error' || true)" "."

# ── 结果汇总 ─────────────────────────────────────────
echo ""
echo "================================================"
echo "  结果：$PASS 通过 / $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
  echo "  🎉 全部通过！主链路正常。"
else
  echo "  ⚠️  有 $FAIL 项失败，请检查上方输出。"
fi
echo "================================================"
echo ""
echo "📋 前端浏览器验收清单（人工）："
echo "  [ ] 欢迎态：居中布局，显示'保险智能体'，无左侧导航"
echo "  [ ] 快捷问题按钮 4 个，点击后正常发送消息"
echo "  [ ] 规划消息 → RouteCard 两个按钮（填写信息规划 / 对话规划）"
echo "  [ ] '填写信息规划' → 跳转 AIX 测算引擎 Module1"
echo "  [ ] 完整需求 → NeedsReportCard 渲染（含预算范围）"
echo "  [ ] 完整需求 → 3 张 RecommendationCard 渲染"
echo "  [ ] ProductCompareCard 可横向滑动"
echo "  [ ] RecommendationConclusionCard 含预算分配格子"
echo "  [ ] RiskDisclosureCard 显示风险提示"
echo "  [ ] 保费显示合理（约数千至两万元/年范围内）"
echo ""
