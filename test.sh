SID=sess_f2e7c5c82646494e8585c49845adbac2
BASE=http://localhost:8002
curl -sS -X POST "$BASE/api/integrated_fields?session_id=$SID" \
  -H "Content-Type: application/json" -d '{"file_id":"any"}' \
| jq '{source, payload:{name:.payload.name, budget:.payload.budget, start:.payload.project_start_date, end:.payload.project_due_date}}'
