# Mission 20: Context Window Management and Compaction Strategy

## Objective

Build the context window management system that tracks token usage across Nala's agent sessions, detects when the context is approaching capacity, and triggers intelligent compaction at the right time rather than waiting for the model to degrade. After this mission, Nala's agents never hit the context wall unprepared, and sessions remain high-quality from start to finish.

## Why This Matters

Context drift is the silent killer of AI agent quality. Research from 2025-2026 shows that nearly 65% of enterprise AI agent failures come from context drift or memory loss during multi-step reasoning, not from raw context exhaustion. Models do not degrade gracefully. They work fine up to an invisible threshold (roughly 80% of their effective window), then recall accuracy drops suddenly. Claude Code learned this the hard way and now compacts at approximately 64% utilization rather than waiting until 90%.

Nala needs to be smarter than the tools it aims to improve upon. It needs to know exactly how much context has been consumed, what is consuming it, and when to compress. It needs to compact proactively at natural breakpoints (between tasks, after completing a function, after a milestone) rather than reactively in the middle of a complex refactor where losing context is most harmful.

The insight from LangChain's Deep Agents project is key: the agent itself should control when to compact, not a rigid threshold. But Nala also provides guardrails so that compaction never triggers at the worst possible moment.

## Context

This system manages context for Nala's AI agent interactions (Mission 12 and 13). When Nala sends prompts to an LLM, the conversation history, tool outputs, codebase context, and system instructions all consume tokens. This mission builds the infrastructure that tracks, manages, and compresses that token budget.

## Implementation Steps

### Step 1: Token counter (context/counter.py)

Build a `TokenCounter` class that estimates token usage for any text. Use tiktoken (for OpenAI-compatible models) or Anthropic's token counting API. For offline estimation, use a simple heuristic: 1 token per 4 characters for English, adjusted for code (code is denser, roughly 1 token per 3.5 characters).

The counter tracks:
- `system_tokens`: Tokens consumed by the system prompt (relatively fixed)
- `context_tokens`: Tokens consumed by injected codebase context (files, symbols, metrics)
- `history_tokens`: Tokens consumed by conversation history (grows with each turn)
- `tool_output_tokens`: Tokens consumed by tool call results (often the largest source of bloat)
- `total_tokens`: Sum of all categories
- `remaining_tokens`: Model max minus total
- `utilization_pct`: total / model_max as a percentage

Expose a `get_usage_breakdown() -> dict` method that returns all categories so the TUI can display them.

### Step 2: Compaction threshold configuration (context/config.py)

Define configurable thresholds:
- `soft_threshold`: 60% utilization. At this point, Nala starts looking for good compaction opportunities. It does not force compaction but begins preparing a background summary.
- `hard_threshold`: 80% utilization. At this point, Nala compacts at the next natural breakpoint (end of current task, after next user message, after tool output is processed).
- `critical_threshold`: 90% utilization. At this point, Nala compacts immediately regardless of what is happening.
- `reserve_buffer`: 10% of the model's context window is always reserved for the model's own reasoning. This space is never consumed by input.

These thresholds are configurable in `.nala/config.toml` but the defaults are based on research showing that quality degrades significantly above 80%.

### Step 3: Compaction opportunity detector (context/detector.py)

Build an `OpportunityDetector` that identifies good moments to compact:
- After a task is completed (user confirmed a change, analysis finished, report saved)
- After a natural conversation break (user has been idle for 30+ seconds)
- When the user starts a new topic (detected by analyzing the semantic shift in the latest message)
- After verbose tool output has been processed and summarized
- When the agent explicitly signals it has completed a sub-task

The detector returns a `CompactionOpportunity` with: reason (str), priority (Low/Medium/High/Critical), current_utilization (float), estimated_savings (float).

Bad times to compact (the detector blocks compaction during these):
- In the middle of a multi-file edit (agent has pending unsaved changes)
- While the agent is mid-reasoning about a complex refactor
- During an active analysis run that has not yet produced results

### Step 4: Compaction engine (context/compactor.py)

Build the `Compactor` that performs the actual context compression when triggered. It uses a tiered approach:

**Tier 1: Tool output pruning** (saves the most tokens with the least information loss)
- Replace verbose tool outputs (file contents, grep results, test output) with compact summaries
- Keep the tool call itself and a 2-3 line summary of what was found
- This alone can recover 30-50% of consumed tokens

**Tier 2: Conversation summarization** (moderate token savings, some information loss)
- Summarize older conversation turns into a structured format:
  - Key decisions made
  - Files modified and what changed
  - Open questions and next steps
  - Important constraints or rules established
- Keep the most recent 3-5 turns verbatim (recent context is highest value)

**Tier 3: Context re-injection** (used after compaction)
- After compacting, re-inject only the most relevant codebase context for the current task
- Use the session's current focus (which files, which functions) to determine what to include
- Do not reload everything that was loaded before compaction

### Step 5: Background summary builder (context/background_summary.py)

Inspired by Claude Code's Session Memory and Deep Agents' autonomous compression, build a background process that continuously maintains a running summary of the current session. This summary is updated after every turn (or every 3 turns to save resources) and is always ready to be used for instant compaction.

The background summary contains:
- Session objective (what the user is trying to accomplish)
- Work completed so far (list of actions taken)
- Current state (what files are open, what the current task is)
- Key decisions and constraints (things the agent must remember)
- Next steps (what was planned but not yet done)

When compaction triggers, the system swaps the full conversation history for this pre-built summary plus the most recent turns. This makes compaction instant rather than requiring a slow re-analysis.

### Step 6: Wire into the TUI

Add context utilization to the status bar:
```
READY | 1,247 files | Context: 45% [████████░░░░░░░░░░░░] 90k/200k
```

Change the color as utilization grows: green (< 60%), yellow (60-80%), red (> 80%).

Add a `/context` command that shows the full breakdown:
```
Context Usage Breakdown:
  System prompt:     2,400 tokens (1.2%)
  CLAUDE.md / rules: 3,100 tokens (1.6%)
  Codebase context: 34,000 tokens (17.0%)
  Conversation:     41,200 tokens (20.6%)
  Tool outputs:     12,800 tokens (6.4%)
  Reserved buffer:  20,000 tokens (10.0%)
  ─────────────────────────────────────
  Total used:       93,500 tokens (46.8%)
  Available:       106,500 tokens (53.2%)
```

Add a `/compact` command that triggers manual compaction with an optional focus parameter:
`/compact` compacts normally
`/compact focus on the auth module refactor` compacts while preserving auth-related context

### Step 7: Write tests

- Test token counting accuracy against known tokenizer output
- Test that the soft/hard/critical thresholds trigger at the right utilization levels
- Test that the opportunity detector blocks compaction during bad times
- Test that the background summary is accurate after a simulated multi-turn conversation
- Test that post-compaction context contains the essential information

## Acceptance Criteria

- Token usage is tracked accurately within 5% of actual model tokenizer output
- Compaction triggers proactively at natural breakpoints, not mid-task
- Background summary is always ready for instant compaction
- Post-compaction sessions maintain coherence (the agent remembers key decisions)
- The TUI shows real-time context utilization
- No source file exceeds 400 lines

## Key Research References

- Claude Code's auto-compaction at ~64% utilization (not 90%)
- LangChain Deep Agents' autonomous compression tool
- Anthropic's compact-2026-01-12 beta API
- Erold's Smart Strip lossless fact extraction
- Zylos Research on context drift killing agents before context limits do

## Estimated Complexity

High. The background summary builder is the hardest part. It needs to produce summaries that preserve critical information without hallucinating or losing important nuance. The compaction opportunity detector requires careful tuning to avoid compacting at bad times.
