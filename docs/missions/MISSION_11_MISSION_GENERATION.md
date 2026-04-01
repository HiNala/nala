# Mission 11: AI Mission Generation

## Objective

Build the mission generation system that analyses the codebase findings and produces a concrete, prioritised improvement plan in the same format as this document — a structured markdown "mission" the developer can follow step-by-step. After this mission, typing `/generate mission` produces a `mission.md` file in the current session that reads like it was written by a senior engineer who spent a day reviewing the codebase.

## Why This Matters

Analysis without action is noise. Every finding from Mission 09 is only valuable if it leads to concrete improvement. Mission generation closes the loop: Nala examines the findings, reasons about priority and impact, and produces a specific, actionable plan with implementation steps, acceptance criteria, and estimated complexity — not a generic list of "code smells."

This is the feature that makes Nala feel like a staff engineer on the team, not just a linter.

## Context

Mission generation uses the LLM (via `AgentOrchestrator`) with a structured prompt that includes:
- The top findings from all perspectives
- The project's language distribution and structure
- Any specific focus area the developer requested (e.g., "focus on the auth module")

The output is saved to `session.mission.md` and displayed in the TUI's message log.

## Implementation Steps

### Step 1: MissionGenerator (agents/mission_generator.py)

```python
class MissionGenerator:
    MISSION_PROMPT = """
You are a senior software engineer performing a code review of {project_name}.
You have just completed an automated analysis and found the following issues:

## Findings Summary
{findings_summary}

## Project Context
{project_context}

{focus_instruction}

Generate a detailed improvement mission in the following format:

# Mission: [descriptive title]

## Objective
[1-2 sentences: what will be fixed/improved and why]

## Why This Matters
[2-3 sentences: business/engineering impact]

## Implementation Steps
[Numbered steps, each with enough detail to act on]

## Acceptance Criteria
[Bulleted checklist of verifiable outcomes]

## Estimated Complexity
[Low / Medium / High, with brief justification]

Be specific: reference actual file names, function names, and line numbers from the findings.
Do not invent findings that were not in the analysis.
"""

    def __init__(self, orchestrator: AgentOrchestrator):
        self.orchestrator = orchestrator

    async def generate(
        self,
        findings: list[PerspectiveResult],
        focus: str = "",
    ) -> AsyncGenerator[str, None]:
        summary = self._format_findings(findings)
        focus_instruction = f"Focus specifically on: {focus}" if focus else ""
        prompt = self.MISSION_PROMPT.format(
            project_name=self.orchestrator.project_name(),
            findings_summary=summary,
            project_context=self.orchestrator.context_summary(),
            focus_instruction=focus_instruction,
        )
        async for chunk in self.orchestrator.stream_query(prompt):
            yield chunk

    def _format_findings(self, results: list[PerspectiveResult]) -> str:
        lines = []
        for r in results:
            if not r.findings:
                continue
            lines.append(f"\n### {r.perspective_name} ({len(r.findings)} findings)")
            # Top 5 findings per perspective, sorted by severity
            top = sorted(r.findings, key=lambda f: ["critical","high","medium","low","info"].index(f.severity))[:5]
            for f in top:
                loc = f" ({f.file_path}:{f.line})" if f.file_path else ""
                lines.append(f"- [{f.severity.upper()}] {f.title}{loc}: {f.description}")
        return "\n".join(lines) or "No significant findings."
```

### Step 2: IPC handler

Add `generate_mission` request type to `cli.py`:

```python
elif req_type == "generate_mission":
    focus = req.get("focus", "")
    findings = agent.session_manager.current().load_findings() if agent.session_manager.current() else []
    generator = MissionGenerator(agent)
    full_text = ""
    async for chunk in generator.generate(findings, focus):
        write_response({"id": req_id, "type": "chunk", "text": chunk})
        full_text += chunk
    # Save to session
    if agent.session_manager.current():
        agent.session_manager.current().save_mission(full_text)
    write_response({"id": req_id, "type": "done"})
```

### Step 3: Rust TUI integration

Add to `handle_slash_command` in `app.rs`:
- `/generate` or `/generate mission` — run analysis first (if not already done), then generate a mission document
- `/generate mission focus <text>` — generate a mission focused on a specific area

The command should:
1. Show "Analysing codebase..." system message
2. Send `run_perspectives` IPC request
3. On completion, send `generate_mission` IPC request
4. Stream the result into the message log
5. Show "Mission saved to session" when done

### Step 4: Mission quality heuristics

After generation, run a brief validation pass to ensure the mission:
- References at least one specific file name (not generic)
- Has at least 3 numbered implementation steps
- Has at least one acceptance criterion
- Is between 300 and 2000 words

If validation fails (e.g., the LLM produced something too short), show a warning and offer to regenerate: "Mission seems incomplete. Type `/generate mission` again to retry."

### Step 5: Mission export

Add a `/export` command that writes the current session's mission to a file in the project root:
- Default filename: `NALA_MISSION_{timestamp}.md`
- The file is ready to paste into a GitHub issue, Linear ticket, or JIRA

### Step 6: Mission history

In the session panel, show a "M" badge next to sessions that have a saved mission document. `/session load <id>` shows the mission if one exists, in addition to the conversation history.

## Acceptance Criteria

- `/generate mission` produces a structured markdown document referencing actual findings
- Generated mission is saved to the current session
- Mission references specific file names and line numbers (not generic advice)
- Focus parameter correctly constrains the scope of the mission
- Generation streams in real time (first chunk within 2 seconds)
- `/export` writes a clean markdown file to the project root
- No file exceeds 400 lines

## Estimated Complexity

Medium. The prompt engineering is the main challenge. Getting the LLM to be specific (reference real files/lines) rather than generic requires careful prompt design and validation.
