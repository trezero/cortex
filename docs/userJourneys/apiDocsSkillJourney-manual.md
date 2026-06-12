# API Docs Skill — Manual Follow-Up Tests

Automated testing (Journeys 1-9) completed on 2026-03-20. These are the remaining
manual tests that require human interaction, a running server, or a fresh Claude Code
session. Each test has exact commands to run and what to look for.

**Branch:** `apiDocsSkill`
**Prerequisite:** The retrofit changes from Journey 5 and the new stats endpoint from
Journey 6 are uncommitted on this branch.

---

## Test A: Runtime Verification (response_model doesn't break endpoints)

**Why:** The retrofit added `response_model=` to 15 endpoints. FastAPI filters response
fields through the model — if the actual return has fields the model doesn't declare,
they get silently dropped. This could break the frontend.

### Steps

1. Restart the backend with the retrofit changes:
   ```bash
   docker compose restart cortex-server
   ```
   Wait for `🎉 Cortex backend started successfully!` in logs:
   ```bash
   docker compose logs -f cortex-server --tail 5
   ```

2. Test endpoints WITH response_model (should return expected shape):
   ```bash
   # ProjectListResponse — should have projects, timestamp, count
   curl -s http://localhost:8181/api/projects | python3 -m json.tool | head -20

   # ProjectCreateResponse — create and check shape
   curl -s -X POST http://localhost:8181/api/projects \
     -H "Content-Type: application/json" \
     -d '{"title": "API Docs Test Project"}' | python3 -m json.tool

   # ProjectHealthResponse — should have status, service, schema
   curl -s http://localhost:8181/api/projects/health | python3 -m json.tool

   # ProjectChildrenResponse
   # (use a real project_id from the list above)
   curl -s http://localhost:8181/api/projects/<PROJECT_ID>/children | python3 -m json.tool

   # New stats endpoint — should have project_id, todo, doing, review, done, total
   curl -s http://localhost:8181/api/projects/<PROJECT_ID>/stats | python3 -m json.tool
   ```

3. Test endpoints WITHOUT response_model (pass-through dicts, should still work):
   ```bash
   # Get single project — returns full project dict
   curl -s http://localhost:8181/api/projects/<PROJECT_ID> | python3 -m json.tool | head -20

   # Task counts — returns dynamic dict keyed by project_id
   curl -s http://localhost:8181/api/projects/task-counts | python3 -m json.tool | head -20

   # List tasks (global)
   curl -s "http://localhost:8181/api/tasks?per_page=2" | python3 -m json.tool | head -20
   ```

4. Check the OpenAPI docs (the whole point of this skill):
   Open http://localhost:8181/docs in a browser.
   - [ ] `/api/projects` shows response schema with field descriptions
   - [ ] `/api/projects` POST shows request body schema with field descriptions
   - [ ] `/api/projects/{project_id}/stats` appears with ProjectStatsResponse schema
   - [ ] Tags sidebar groups "projects" and "tasks" endpoints separately
   - [ ] Error responses (404, 500) appear in each endpoint's response section

### What to look for

- **PASS if:** All endpoints return data as before. The `/docs` page shows schemas.
- **FAIL if:** Any endpoint returns an empty object `{}`, drops fields that the
  frontend needs, or throws a 500 error that wasn't there before.
- **Common failure:** A `response_model` with strict fields filtering out dynamic
  Supabase columns. Fix: add `model_config = ConfigDict(extra="allow")` to that model
  or remove the `response_model` from that endpoint.

---

## Test B: Natural Skill Triggering (fresh session)

**Why:** The automated tests followed the skill instructions manually. This tests
whether Claude Code naturally discovers and follows the skill when given a relevant task.

### Steps

1. Start a **new Claude Code session** in the Cortex repo (same branch):
   ```bash
   claude
   ```

2. **Test B1 — Intercept mode trigger.** Type:
   ```
   Add a GET /api/projects/{project_id}/collaborators endpoint that returns
   a list of system registrations for the project
   ```
   - [ ] Claude invokes the `api-docs` skill (you should see "Using api-docs" or similar)
   - [ ] The endpoint comes out with `response_model`, `status_code`, `tags`, `responses`
   - [ ] A Pydantic response model is created with `Field(description=...)` on every field
   - [ ] The response model has `json_schema_extra` example
   - [ ] Claude mentions or invokes Postman integration after creating the endpoint

3. **Test B2 — Retrofit mode trigger.** In the same or new session, type:
   ```
   Audit the API documentation on the knowledge endpoints
   ```
   - [ ] Claude invokes the `api-docs` skill
   - [ ] Claude scans `knowledge_api.py` and reports gap count
   - [ ] Claude asks "dry-run report first, or fix them all?"

4. **Test B3 — Explicit trigger.** Type:
   ```
   /api-docs
   ```
   - [ ] Skill activates
   - [ ] Claude asks whether to intercept or retrofit

5. **Test B4 — Non-trigger.** Type:
   ```
   Add a new React component that displays project statistics in a dashboard card
   ```
   - [ ] The `api-docs` skill does NOT activate
   - [ ] No mention of response_model, OpenAPI docs, or endpoint documentation

### What to look for

- **PASS if:** B1-B3 activate the skill; B4 does not.
- **FAIL if:** The skill doesn't activate on endpoint-related requests, or activates
  on frontend-only requests.

---

## Test C: Guard — Non-FastAPI Project

**Why:** Journey 2.2 was simulated. This tests the actual guard skip behavior.

### Steps

1. Navigate to a non-FastAPI project directory. If you don't have one handy, use the
   frontend directory:
   ```bash
   cd /home/winadmin/projects/Trinity/cortex/cortex-ui
   claude
   ```

2. Type:
   ```
   Use the api-docs skill to audit the API endpoints
   ```
   - [ ] Output includes: "Skipping API documentation — no FastAPI endpoints detected
     in this project."
   - [ ] No further scanning or gap reporting happens

### What to look for

- **PASS if:** The skip message appears and Claude stops.
- **FAIL if:** Claude proceeds to scan files or reports false positives.

---

## Test D: Multiple FastAPI Apps Detection

**Why:** Cortex has 3 FastAPI() instances. The skill should ask which app to target
when doing a full-repo retrofit.

### Steps

1. In a fresh session on the Cortex repo, type:
   ```
   Use the api-docs skill to document all API endpoints in this entire repo
   ```
   - [ ] Claude detects multiple FastAPI() instances (main server, agent_work_orders,
     agents)
   - [ ] Claude asks which app to target before proceeding

### What to look for

- **PASS if:** Claude asks before proceeding.
- **FAIL if:** Claude silently picks one app or tries to retrofit all three at once.

---

## Test E: Pydantic v2 Syntax Verification

**Why:** The skill claims to detect Pydantic version and use appropriate syntax.
Verify the retrofit output uses v2 patterns exclusively.

### Steps

1. In the retrofitted `projects_api.py`, search for any v1 patterns:
   ```bash
   grep -n "class Config:" python/src/server/api_routes/projects_api.py
   grep -n "schema_extra" python/src/server/api_routes/projects_api.py
   ```
   - [ ] Zero matches for `class Config:`
   - [ ] Zero matches for `schema_extra` (should be `json_schema_extra` everywhere)

2. Confirm v2 patterns are used:
   ```bash
   grep -c "json_schema_extra" python/src/server/api_routes/projects_api.py
   grep -c "ConfigDict" python/src/server/api_routes/projects_api.py
   ```
   - [ ] `json_schema_extra` count > 0
   - [ ] `ConfigDict` count > 0

### What to look for

- **PASS if:** Only v2 syntax found.
- **FAIL if:** Any v1 patterns (`class Config`, `schema_extra` without `json_` prefix).

---

## Test F: Retrofit Preserves Existing (Idempotency)

**Why:** Running retrofit a second time should not change already-documented endpoints.

### Steps

1. After Test A passes, in a fresh session type:
   ```
   Use the api-docs skill to audit just the projects API endpoints
   ```
   - [ ] Claude reports zero (or very few) documentation gaps
   - [ ] No changes are proposed to already-documented endpoints

### What to look for

- **PASS if:** The skill recognizes existing documentation and reports no gaps.
- **FAIL if:** The skill proposes re-documenting endpoints that are already fully
  documented.

---

## Cleanup

After all tests pass:

1. **Decide what to keep.** The retrofit changes to `projects_api.py` are real code
   improvements. Options:
   - Keep them on this branch and merge with the skill
   - Revert them (`git checkout HEAD -- python/src/server/api_routes/projects_api.py`)
     and keep only the skill definition
   - Move them to a separate branch/PR

2. **Delete the test project** created in Test A step 2:
   ```bash
   curl -X DELETE http://localhost:8181/api/projects/<TEST_PROJECT_ID>
   ```

3. **Revert the stats endpoint** if it was only for testing:
   The `GET /api/projects/{project_id}/stats` endpoint and its Postman YAML were
   created as a test artifact. Remove if not wanted in the final merge.

---

## Results

| Test | Status | Tester | Date | Notes |
|------|--------|--------|------|-------|
| A. Runtime Verification | PASS | Claude | 2026-03-20 | All endpoints return correct shapes. ProjectListResponse (89 projects, timestamp, count), ProjectHealthResponse (healthy), ProjectStatsResponse (6 fields), TaskListResponse (pagination works), ProjectChildrenResponse, DELETE 404 works. OpenAPI spec at /openapi.json has all 5 checked response models with correct properties. |
| B1. Intercept Trigger | | | | |
| B2. Retrofit Trigger | | | | |
| B3. Explicit Trigger | | | | |
| B4. Non-Trigger | | | | |
| C. Guard Skip | | | | |
| D. Multiple Apps | | | | |
| E. Pydantic v2 Syntax | PASS | Claude | 2026-03-20 | Zero `class Config:` matches (v1). Zero bare `schema_extra` (v1). 15 `json_schema_extra` (v2). 17 `ConfigDict` (v2). |
| F. Idempotency | | | | |
