#!/bin/bash
# all tests one after another; a summary line per test
cd "$(dirname "$0")/.."            # the checkout this script is in (also a worktree)
mkdir -p tools/t; OUT=tools/t/run_all.out
: > $OUT
for t in ${TESTS:-hook_test work_test family_test combo_test edge_test edge_test_left edge_test_resize throw_test console_test nap_test grow_test chore_test dig_test play_test album_test talk_test circle_test circle_edge_test ag_sub_test dsh_test connect_test}; do
  start=$(date +%s)
  C:/Python312/python.exe tools/$t.py > tools/t/$t.out 2>&1
  code=$?
  echo "$t exit=$code secs=$(( $(date +%s) - start )) :: $(grep -E 'passed|FAIL|Error|rror' tools/t/$t.out | tail -3 | tr '\n' ' ')" >> $OUT
done
echo ALL DONE >> $OUT
