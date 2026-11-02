#!/usr/bin/env bash
BASE=http://127.0.0.1:8000
S=$(curl -s -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"role":"student","username":"2024010101","password":"123456"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
T=$(curl -s -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"role":"teacher","username":"T1001","password":"123456"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "== 学生端 =="
for p in menu profile grades timetable exams notifications messages free-classrooms enrollments calendar greeting makeup applications training-plan textbooks electives academic-status selection-list; do
  printf "%s %s\n" "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $S" $BASE/api/student/$p)" "/api/student/$p"
done
echo "== 教师端 =="
for p in menu profile classes students grades grades/analysis timetable meetings messages proctor textbooks schedule/pending schedule/requests; do
  printf "%s %s\n" "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $T" $BASE/api/teacher/$p)" "/api/teacher/$p"
done
echo "== 静态 =="
printf "%s /\n" "$(curl -s -o /dev/null -w '%{http_code}' $BASE/)"
echo "== 慢请求统计 =="
curl -s $BASE/api/health
