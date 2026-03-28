# Beginner Coach UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing assistant into a beginner-friendly Slay the Spire coach that teaches card evaluation and build direction while still giving clear current-turn recommendations.

**Architecture:** Keep the existing API and recommendation pipeline intact, add teaching-oriented metadata and stronger fallback chat reasoning on the Python side, then reshape the Vue UI to surface “what to do / why / what you learn” first. Reuse existing build-profile and recommendation data rather than introducing a separate beginner mode.

**Tech Stack:** Python standard library, pytest, Vue 3, TypeScript, Vite

---

## File Map

- Modify: `sts_ai_assistant/service/rule_based_advisor.py`
  - Add beginner-coach metadata for recommendation replies and stronger rule-based chat fallback.
- Modify: `sts_ai_assistant/service/assistant_service.py`
  - Preserve or synthesize teaching-style reasons when the model reply is too generic.
- Create: `tests/test_beginner_coach.py`
  - Regression tests for teaching metadata and non-generic chat fallback.
- Modify: `frontend/src/App.vue`
  - Reshape the assistant panel into a teaching-first layout and add quick question templates.

### Task 1: Backend Regression Tests For Beginner Coaching

**Files:**
- Create: `tests/test_beginner_coach.py`
- Read: `sts_ai_assistant/service/rule_based_advisor.py`
- Read: `sts_ai_assistant/service/assistant_service.py`

- [ ] **Step 1: Write failing tests for recommendation teaching metadata**

Write tests that build a small `GameSnapshot` for card reward and assert the rule-based analysis exposes beginner-oriented raw metadata such as a teaching rule, a “this pick is补什么” explanation, and a safe default line.

- [ ] **Step 2: Write failing tests for non-generic chat fallback**

Write tests that ask questions like `我现在这套牌缺什么？` and `为什么不删牌` and assert the reply has a concrete conclusion plus at least two reasons tied to current run context.

- [ ] **Step 3: Run the focused test file and confirm failure**

Run: `.\.venv\Scripts\python -m pytest tests/test_beginner_coach.py -q`
Expected: FAIL because the new beginner-coach metadata and chat fallback behavior do not exist yet.

- [ ] **Step 4: Implement only the minimum backend behavior needed to satisfy the failing tests**

Add the teaching metadata and targeted chat fallback logic without changing API shape.

- [ ] **Step 5: Re-run the focused backend tests**

Run: `.\.venv\Scripts\python -m pytest tests/test_beginner_coach.py -q`
Expected: PASS.

### Task 2: Frontend Teaching-First Assistant Panel

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add computed helpers for beginner-coach display state**

Use the existing reply plus backend raw metadata to compute:
- current learning rule
- what the recommended pick fixes
- safe default line
- white-language build labels
- quick question templates

- [ ] **Step 2: Update the assistant panel layout**

Restructure the main area so it reads in this order:
- 现在就点
- 为什么
- 不这样选会亏什么
- 这次学到的判断规则
- 拿不准时先怎么选

- [ ] **Step 3: Update the build card wording**

Keep the same data, but relabel it into beginner language:
- 这局现在先学什么
- 接下来两场重点找什么
- 现在先别拿什么
- 什么时候再换路线

- [ ] **Step 4: Add quick question templates to the chat area**

Add click-to-fill or click-to-send templates for:
- 这层该拿牌还是跳过？
- 我现在这套牌缺什么？
- 接下来两场我该找什么？
- 为什么这次更推荐删牌？
- 这回合先出哪几张？

- [ ] **Step 5: Build the frontend to verify the UI still compiles**

Run: `npm.cmd --prefix frontend run build`
Expected: exit 0.

### Task 3: End-To-End Verification

**Files:**
- Read: `docs/superpowers/specs/2026-03-28-beginner-coach-ux-design.md`
- Read: modified backend/frontend files

- [ ] **Step 1: Verify spec coverage**

Check that the implementation now covers:
- teaching-first recommendation block
- beginner white-language build labels
- quick chat templates
- non-generic fallback chat reasoning

- [ ] **Step 2: Run Python compile verification**

Run: `.\.venv\Scripts\python -m compileall sts_ai_assistant`
Expected: exit 0.

- [ ] **Step 3: Re-run frontend build**

Run: `npm.cmd --prefix frontend run build`
Expected: exit 0.

- [ ] **Step 4: Summarize remaining risk honestly**

If there is no frontend unit-test harness, call that out explicitly and state that the UI was verified by build/typecheck plus backend regression tests.
