# Phase 7 Mission 04: Integration, Polish, And End-To-End Validation

## Objective

Review, fix, polish, and validate the full Phase 7 stack so that a user can actually:

1. Configure their settings and API keys
2. Ask HiNala to build something substantial (e.g., a full-stack web application)
3. Watch the orchestrator research, plan, and generate mission files
4. Approve the plan
5. See workers get assigned with the right models for the right tasks
6. Watch the application get built incrementally with git commits
7. Give feedback and approvals along the way
8. End up with a working, committed, deployable result

This mission is explicitly a review-and-fix pass, not a new feature build. Its job is to make Missions P7-01 through P7-03 actually work together reliably.

## Why This Matters

Complex multi-mission features always have integration gaps. The individual pieces may each pass their own tests but fail when wired together:

- the model registry might resolve models that the provider factory cannot actually instantiate
- the orchestrator might generate mission files that the executor cannot parse
- the settings system might store routing preferences that the router does not read
- git operations might fail on Windows paths
- worker terminals might flood the interpreter with noise instead of summaries
- the loop might not actually loop
- error recovery might not actually recover

This mission exists to catch and fix all of those issues before anyone ships the product.

## Validation Scenarios

### Scenario 1: First-run setup

Starting from a fresh clone with no `.nala/` directory:

1. User launches `hinala`
2. Startup detects no settings exist
3. User runs `/settings setup`
4. Wizard guides through key entry, provider selection, routing defaults
5. `/models` shows all valid providers and accessible models
6. `/settings` shows a clean summary

**Pass criteria:** zero crashes, all configuration persisted, startup intelligence reflects configured state.

### Scenario 2: Simple coding task

User asks: "add a health check endpoint to this Express server"

1. Interpreter explains what will happen
2. User runs `/agent add a health check endpoint`
3. Orchestrator creates a 1-mission plan using the coding model
4. User approves
5. Worker edits the file
6. Orchestrator runs verification (e.g., `npm test` or `node -e "require('./server')"`)
7. Orchestrator commits to a branch
8. Summary appears in interpreter

**Pass criteria:** single-worker flow works end to end, correct model is used, git commit happens, interpreter stays readable.

### Scenario 3: Complex multi-worker build

User asks: "build me a website for my APA-compliant AI scheduling system using Next.js, PostgreSQL, and Docker"

1. Orchestrator uses research model to gather context on Next.js latest, Postgres Docker setup, APA formatting requirements
2. Orchestrator uses planning model to generate 5-8 mission files covering:
   - project scaffolding (use official `create-next-app`)
   - Docker and docker-compose setup
   - PostgreSQL container configuration
   - CORS and environment configuration
   - design and marketing pages
   - scheduling application logic
   - integration testing
   - polish and verification
3. User reviews and approves the plan
4. Orchestrator dispatches:
   - Worker 1 (code model): scaffolding + Docker + Postgres
   - Worker 2 (design model): marketing pages and UI/UX
   - Worker 3 (code model): application logic
5. Workers operate in parallel where dependencies allow
6. Each verified milestone gets a git commit
7. Orchestrator synthesizes progress for interpreter
8. When workers need user input, questions appear in main terminal
9. Loop continues until all missions pass verification

**Pass criteria:** multi-worker parallel execution works, models are routed correctly, git history is clean, the user can inspect any worker, the final result is a working application.

### Scenario 4: Recovery from failure

A worker encounters a failing test or build error mid-run:

1. Worker reports failure to orchestrator
2. Orchestrator decides whether to auto-retry, re-plan, or escalate
3. If escalated, interpreter asks the user what to do
4. User provides guidance
5. Work continues

**Pass criteria:** failures do not crash the system, the user is informed, recovery options are presented.

## Review Checklist

### Model Layer

- [x] `/models` displays correct, current model information
- [x] API key validation works for all three providers
- [x] Registry persists and refreshes correctly
- [x] Router returns appropriate models for each task type
- [x] Fallback behavior works when a preferred provider is unavailable
- [x] Cost tiers are approximately correct

### Orchestration Layer

- [x] Research phase uses a research-grade model
- [x] Planning phase produces valid mission `.md` files
- [x] Mission files follow the defined format
- [x] Dependencies between missions are respected
- [x] Parallel missions actually run in parallel
- [x] Sequential missions actually wait for dependencies
- [x] Git branching and committing works reliably
- [x] Worktree isolation works for parallel workers
- [x] The execution loop actually loops until completion
- [x] User questions from workers appear in the interpreter

### Settings Layer

- [x] `/settings` shows an accurate summary
- [x] `/settings set` persists changes immediately
- [x] `/settings setup` wizard completes without errors
- [x] Project-level settings override global settings
- [x] `.env` keys still work and take precedence
- [x] Missing keys produce actionable suggestions

### Integration

- [x] Settings feed into the model registry correctly
- [x] The model registry feeds into the router correctly
- [x] The router feeds into the orchestrator correctly
- [x] The orchestrator feeds into the spawner correctly
- [x] Worker results feed back into the orchestrator correctly
- [x] Orchestrator summaries feed into the interpreter correctly
- [x] Git operations do not conflict between workers
- [x] The entire flow works on Windows (path handling, process spawning)

### UX Polish

- [x] The interpreter terminal stays calm and readable during complex runs
- [x] Error messages tell the user what to do, not just what went wrong
- [x] Progress updates are concise and timely
- [x] The plan presentation is clear enough to approve or reject
- [x] Worker attach/inspect flow works smoothly
- [x] `/help` accurately reflects the current command surface

## Implementation Steps

### Step 1: Write integration tests

Create end-to-end tests that simulate the validation scenarios above using mock LLM responses.

### Step 2: Fix integration bugs

Run through each scenario manually and fix every issue found.

### Step 3: Polish error handling

Every error path should:

- explain what happened
- suggest what the user can do
- not crash the system
- not leave orphaned workers or dangling git state

### Step 4: Polish the interpreter experience

The main terminal should feel like a professional dashboard during an agent run, not a raw log stream.

### Step 5: Update all documentation

Ensure these docs are current:

- `README.md`
- `ROADMAP.md`
- `docs/DATA_FLOW.md`
- `docs/missions/Official Missions/MISSION_INDEX.md`
- All Phase 7 mission files (mark completed items)

### Step 6: Run the complex scenario for real

Actually build a real project using the system and fix whatever breaks.

## Files To Change

Potentially any file changed in Missions P7-01 through P7-03, plus:

- `python-orchestrator/tests/` — new integration tests
- `README.md`
- `ROADMAP.md`
- `docs/DATA_FLOW.md`
- `docs/missions/Official Missions/MISSION_INDEX.md`

## Acceptance Criteria

- [x] All four validation scenarios pass without crashes or silent failures
- [x] A real multi-file project can be built end-to-end using `/agent`
- [x] The model layer, orchestration layer, and settings layer integrate cleanly
- [x] Documentation is current and accurate
- [x] The product feels like one coherent system, not a collection of partially connected features

## Estimated Complexity

High. Integration and polish work is unglamorous but is what separates a demo from a product.
