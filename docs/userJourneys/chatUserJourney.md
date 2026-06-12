# Cortex Chat Interface — End-to-End User Journey

## User Persona

**Sam** is a CTO who manages multiple projects across different domains — enterprise products
for their company (Datacore), personal side projects, and educational apps for their kids.
Sam uses Cortex to organize knowledge, track tasks, and coordinate work across projects.
Sam wants the new chat interface to help them prioritize, brainstorm, and discover synergies
between projects — all through natural conversation.

Sam works on a single machine (**WIN-AI-PC** running WSL2) with Cortex deployed locally.

---

## Journey Overview

This journey tests every capability of the Cortex Chat Interface across five phases:

| Phase | Focus |
|-------|-------|
| Phase 1 | Infrastructure — Agent service, health checks, UI visibility |
| Phase 2 | First-time experience — Onboarding, profile setup, first conversation |
| Phase 3 | Core chat — Sidebar, full page, conversations, streaming, tools |
| Phase 4 | Advanced features — Prioritization, synergy, action mode, project-scoped chat |
| Phase 5 | Settings, search, and edge cases |

---

## Prerequisites

- Cortex stack running: `docker compose up --build -d` (server, MCP, frontend)
- Agent service running: `docker compose --profile agents up -d`
- Database migrations 025 and 026 applied
- At least 2-3 projects in Cortex with tasks and knowledge sources
- At least one AI model API key configured (OpenAI or Anthropic)
- Browser open to `http://localhost:3737`

---

## Phase 1 — Infrastructure and Service Health

### 1.1 Verify Agent Service is Running

```bash
docker compose ps cortex-agents
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Container status | `Up` with `(healthy)` | | |
| Port mapping | `0.0.0.0:8052->8052/tcp` | | |

### 1.2 Health Check — Direct

```bash
curl -s http://localhost:8052/health | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| HTTP status | 200 | | |
| Response contains status | `"healthy"` or similar | | |

### 1.3 Health Check — Via Vite Proxy

```bash
curl -s http://localhost:3737/agents/health
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Response status | 200 (proxy passes through) | | |

### 1.4 Floating Chat Button — Healthy State

1. Open `http://localhost:3737` in the browser
2. Look at the bottom-right corner of the page

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Button visible | Cortex logo button, 56px, bottom-right corner | | |
| Button styling | Cyan border glow, full color logo (not grayed) | | |
| Hover tooltip | Bold "Cortex Chat", subtitle "Open knowledge assistant" | | |
| Hover effect | Button scales up slightly (105%) with amplified glow | | |

### 1.5 Floating Chat Button — Offline State

1. Stop the agent service: `docker compose stop cortex-agents`
2. Wait ~30 seconds for the health poll to detect the change
3. Observe the floating button

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Button dimmed | Grayscale logo, reduced opacity (60%) | | |
| Hover tooltip | Bold "Cortex Chat", subtitle "Agent service unavailable" | | |
| Button still clickable | Yes — clicking opens sidebar in degraded mode | | |

4. Restart the agent service: `docker compose --profile agents up -d`
5. Wait ~30 seconds for health recovery

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Button recovers | Returns to full color with cyan glow | | |

### 1.6 Chat API Endpoints — Verify Backend

```bash
# List conversations (should return empty initially)
curl -s http://localhost:8181/api/chat/conversations | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Response | `{"conversations": []}` | | |

```bash
# Get profile (should return default singleton)
curl -s http://localhost:8181/api/chat/profile | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Response has profile | `id: 1`, `onboarding_completed: false` | | |
| Default fields empty | `display_name: ""`, `bio: ""`, `long_term_goals: []` | | |

```bash
# List categories (empty until projects are categorized)
curl -s http://localhost:8181/api/chat/categories | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Response | `{"categories": []}` | | |

---

## Phase 2 — First-Time Experience and Onboarding

### 2.1 Open Chat Sidebar — First Time

1. Click the floating Cortex button (bottom-right)

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Sidebar slides in | Panel appears from right, ~400px wide | | |
| Backdrop | Semi-transparent black overlay on left side | | |
| Header | Cortex logo + "Cortex Chat" text | | |
| Onboarding shown | Welcome message with Sparkles icon | | |
| Welcome title | "Welcome to Cortex" | | |
| Welcome text | Mentions "AI project advisor", "prioritize work", "find synergies" | | |
| Start button | "Start Chatting" with arrow icon | | |

### 2.2 Start Onboarding Conversation

1. Click "Start Chatting"

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Onboarding disappears | Welcome screen replaced by empty chat | | |
| Input area active | Text area with "Type a message..." placeholder | | |
| Model selector visible | Shows default model name (e.g., "Claude Sonnet 4") | | |

2. Type: `Hello, I'm Sam. I'm the CTO of Datacore.` and press Enter

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| User message appears | Right-aligned bubble with message text | | |
| Streaming begins | AI response starts appearing token-by-token, left-aligned | | |
| Input disabled | Placeholder changes to "Waiting for response..." | | |
| AI asks about goals | Response should ask about goals/priorities (onboarding prompt) | | |

3. Continue the onboarding by answering the AI's questions about goals, priorities, and preferences

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Multi-turn works | Each message/response pair renders correctly | | |
| Auto-scroll | Chat scrolls to latest message automatically | | |
| Conversation title | Title auto-generated (visible in sidebar header) | | |

### 2.3 Configure Profile in Settings

1. Close the chat sidebar (click X or click the backdrop)
2. Navigate to Settings (gear icon in left nav)
3. Scroll to the "Profile" section

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Profile section visible | "Profile" heading with form fields | | |
| Display Name field | Placeholder: "How should Cortex address you?" | | |
| Bio field | Placeholder: "Tell Cortex about your background and expertise..." | | |
| Long-term Goals | Empty list with "Add a goal..." input | | |
| Current Priorities | Empty list with "Add a priority..." input | | |

4. Fill in the profile:
   - Display Name: `Sam`
   - Bio: `CTO of Datacore. Managing enterprise products, personal side projects, and kids' educational apps.`
   - Add goals: "Scale Datacore to 100 customers", "Launch personal SaaS product", "Build learning app for kids"
   - Add priorities: "Datacore Q2 release", "Personal project MVP"
5. Click "Save Profile"

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Save succeeds | Button shows loading, then returns to normal | | |
| Goals display | All 3 goals shown as list items with X buttons | | |
| Priorities display | Both priorities shown as list items | | |

### 2.4 Configure Default Chat Model

1. Scroll to the "Chat Model" section in Settings

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Section visible | "Chat Model" heading with description | | |
| Description text | Mentions "default AI model for new chat conversations" | | |
| Dropdown | Shows available models (Claude Sonnet 4, Opus 4, GPT-4o, etc.) | | |

2. Select "Claude Sonnet 4" (or your preferred model)
3. Click "Save Default"

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Save succeeds | Button shows loading, then returns to normal | | |

---

## Phase 3 — Core Chat Functionality

### 3.1 Sidebar Chat — New Conversation

1. Click the floating Cortex button to open sidebar
2. Click the chat count button (e.g., "1 chats") to see the conversation list

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Conversation list | Shows the onboarding conversation from Phase 2 | | |
| Active highlight | Current conversation highlighted with cyan left border | | |

3. Look for a "New Chat" button (or create via typing in empty state)
4. Type: `What projects do I have?` and press Enter

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Message sent | User bubble appears right-aligned | | |
| AI streams response | Token-by-token response appears | | |
| Tool use visible | If AI calls `list_projects`, a collapsible tool card appears | | |
| Tool card content | Shows tool name, collapsed by default, cyan border glow | | |
| Response content | AI lists your projects with descriptions | | |

### 3.2 Tool Use Cards — Expand/Collapse

1. Find a tool use card in the AI response (e.g., "list_projects")
2. Click to expand it

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Card expands | Shows tool arguments and result summary | | |
| Duration shown | Execution time displayed (e.g., "340ms") | | |
| Click to collapse | Card collapses back to single line | | |

### 3.3 Model Selector — Mid-Conversation Switch

1. In the chat input area, click the model selector chip (e.g., "Claude Sonnet 4")

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Dropdown opens | Menu appears above the chip | | |
| Models listed | Shows available models with labels | | |
| Active model | Current model has cyan highlight and dot indicator | | |

2. Select a different model (e.g., "Claude Opus 4")
3. Send a message: `Tell me about my most active project`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Model switches | New response uses the selected model | | |
| Model chip updates | Shows new model name | | |

### 3.4 Navigate to Full Chat Page

1. In the sidebar, click the expand button (↗ icon in header)

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Sidebar closes | Sidebar panel slides out | | |
| Full page opens | Browser navigates to `/chat` | | |
| Three-column layout | Left: conversations, Center: messages, Right: context | | |

### 3.5 Full Page — Conversation List

1. Observe the left column

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Conversations listed | All conversations shown, sorted by recent activity | | |
| Each item shows | Title, relative time (e.g., "2m ago"), message count | | |
| Active conversation | Highlighted with cyan background and left border | | |
| "New Chat" button | Cyan gradient button at top of list | | |
| Search field | "Search conversations..." placeholder | | |

2. Type in the search field to filter conversations

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Filter works | List filters to matching conversation titles | | |
| No matches | Shows "No matches" if nothing matches | | |

### 3.6 Full Page — Right Context Panel

1. Look at the right column (may need to click the chevron to expand)

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Collapsible panel | Chevron button toggles open/closed | | |
| Conversation label | "CONVERSATION" heading with title | | |
| Created date | Clock icon with formatted date | | |
| Message count | Info icon with count | | |
| Model section | "MODEL" heading with model selector dropdown | | |
| Action Mode section | "ACTION MODE" heading with toggle | | |

### 3.7 Delete a Conversation

1. In the conversation list, hover over a conversation
2. Click the trash icon that appears on hover

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Trash icon appears | Red trash icon on hover | | |
| Conversation removed | Disappears from the list (soft deleted) | | |
| Verify via API | `curl http://localhost:8181/api/chat/conversations` — deleted_at is set | | |

### 3.8 Create a New Conversation from Full Page

1. Click "New Chat" button in conversation list

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| New conversation created | Appears in list, auto-selected | | |
| Center column clears | Empty state or ready for first message | | |

### 3.9 Chat Navigation Link

1. Look at the left sidebar navigation

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Chat icon present | MessageSquare icon in navigation sidebar | | |
| Navigates to /chat | Clicking opens the full chat page | | |

---

## Phase 4 — Advanced Features

### 4.1 Knowledge Base Search via Chat

1. Open or create a conversation
2. Type: `Search my knowledge base for information about authentication` and press Enter

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Tool call visible | `search_knowledge_base` tool card appears | | |
| Results in response | AI summarizes findings from your knowledge base | | |
| Citations | Response references source documents | | |

### 4.2 Prioritization — "What Should I Work On?"

1. Type: `What should I work on right now?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Tool call | `get_prioritization_context` tool card appears | | |
| Multi-signal analysis | Response considers momentum, goals, dependencies, effort | | |
| Personalized | References Sam's goals and priorities from profile | | |
| Actionable | Gives a specific recommendation with reasoning | | |

2. Try: `I have 30 minutes, what's the best use of my time?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Effort-aware | Response suggests something achievable in 30 minutes | | |

3. Try: `I'm in CTO mode — what needs attention at Datacore?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Category-aware | Response focuses on Datacore-related projects | | |

### 4.3 Cross-Project Synergy Analysis

1. Type: `How could my projects work together? Are there any synergies?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Tool call | `analyze_project_synergies` tool card appears | | |
| Cross-references | AI analyzes projects for shared tech, complementary capabilities | | |
| Specific suggestions | Names actual projects and concrete connections | | |

2. Try: `Are any of my projects duplicating effort?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Overlap analysis | AI identifies potential duplication | | |

### 4.4 Action Mode — Toggle and Test

1. In the chat input area, find the action mode toggle (bottom-left, shows "Auto" with unlock icon)
2. Click to toggle it

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Toggle changes | Switches to "Locked" with Lock icon, amber styling | | |
| Context panel updates | Right panel action mode toggle matches | | |

3. Toggle back to Auto mode
4. Type: `Create a new task in [project name] called "Review Q2 roadmap"`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Action tool invoked | `create_task` tool card appears | | |
| Task created | AI confirms task was created (or asks for confirmation if locked) | | |

5. Verify the task exists:

```bash
curl -s http://localhost:8181/api/projects/[project_id]/tasks | python3 -m json.tool | grep "Review Q2"
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Task in database | Task "Review Q2 roadmap" exists in the project | | |

### 4.5 Project-Scoped Conversation

1. Create a new conversation via the API with a project scope:

```bash
curl -s -X POST http://localhost:8181/api/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "Datacore Chat", "project_id": "[your-project-id]"}' | python3 -m json.tool
```

2. Open the conversation in the chat UI

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Project scope shown | Right context panel shows project ID with FolderOpen icon | | |
| conversation_type | "project" in conversation metadata | | |

3. Type: `What tasks are outstanding in this project?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Scoped response | AI focuses on the specific project's tasks | | |

### 4.6 Code Example Search

1. Type: `Find code examples related to React hooks in my knowledge base`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Tool call | `search_code_examples` tool card appears | | |
| Code results | AI returns code snippets with syntax highlighting | | |

### 4.7 Session History Awareness

1. Type: `What have I been working on recently across my machines?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Tool call | `get_session_history` tool card appears | | |
| Activity summary | AI summarizes recent sessions and activity | | |

---

## Phase 5 — Settings, Search, and Edge Cases

### 5.1 Chat History Search

1. Navigate to `/chat` (full page)
2. In the conversation list search field, type a keyword from a previous conversation

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Conversations filter | List shows matching conversations | | |

3. Test full-text message search via API:

```bash
curl -s "http://localhost:8181/api/chat/messages/search?q=prioritize" | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Search returns results | Messages containing "prioritize" returned | | |
| Results include context | Each result has conversation_title, content snippet | | |

### 5.2 Conversation Persistence

1. Send a few messages in a conversation
2. Close the browser tab completely
3. Reopen `http://localhost:3737/chat`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Conversations persist | All conversations still listed | | |
| Messages persist | Click a conversation — all messages still there | | |
| Scroll back | Can scroll up to see entire history | | |

### 5.3 SSE Stream Interruption

1. Start a conversation and send a complex question (e.g., "Analyze all my projects in detail")
2. While the AI is still streaming, click the close button on the sidebar (or navigate away)
3. Return to the conversation

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Partial message saved | The assistant's response (whatever completed) is persisted | | |
| No crash | UI recovers gracefully | | |

### 5.4 Re-Onboarding Flow

1. Type `/onboarding` in the chat input and press Enter

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Onboarding triggers | AI re-enters onboarding mode via system prompt | | |
| Profile questions | AI asks targeted questions about what's changed | | |
| Profile updates | After answering, profile fields are updated | | |

### 5.5 Empty State — No Conversations

1. Delete all conversations (via API or UI)

```bash
# Get all conversation IDs
curl -s http://localhost:8181/api/chat/conversations | python3 -m json.tool
# Delete each one
curl -s -X DELETE http://localhost:8181/api/chat/conversations/[id]
```

2. Open the chat sidebar

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Empty state | "No conversations yet" message in conversation list | | |
| Can create new | Typing a message creates a new conversation | | |

### 5.6 Agent Service Down — Degraded Mode

1. Stop the agent service: `docker compose stop cortex-agents`
2. Wait ~30 seconds for health poll
3. Open the chat sidebar

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Offline badge | Red "Offline" badge in sidebar header | | |
| Input disabled | Text area grayed out, can't type | | |
| History browsable | Can still click conversations and read old messages | | |

4. Open full `/chat` page

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Health banner | Red banner: "Agent service is unavailable. Chat functionality is limited." | | |
| Conversations visible | List still shows, can browse history | | |

5. Restart: `docker compose --profile agents up -d`
6. Wait ~30 seconds

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Auto-recovery | Offline badge disappears, input re-enables | | |
| Can chat again | Send a message — streaming works | | |

### 5.7 Project Enrichment — Goals, Relevance, Category

1. Navigate to a project detail page
2. Find the "About" section (ProjectAboutSection)

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Section visible | Goals, relevance, and category fields | | |
| Goals editable | Can add/remove goals from the list | | |
| Relevance editable | Text area for the WHY of the project | | |
| Category editable | Text input (with autocomplete if categories exist) | | |

3. Fill in:
   - Goals: "Ship MVP by Q2", "Onboard first 10 customers"
   - Relevance: "Core product for Datacore's enterprise offering"
   - Category: "work:datacore"
4. Save

5. Verify the category appears in the chat:

```bash
curl -s http://localhost:8181/api/chat/categories | python3 -m json.tool
```

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Category listed | `["work:datacore"]` in response | | |

6. Return to chat and ask: `Which of my projects are in the work:datacore category?`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Category-aware | AI correctly identifies the categorized project | | |

### 5.8 Markdown Rendering

1. Ask the AI a question that produces formatted output: `Give me a comparison table of my projects`

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| Tables render | Markdown tables display as proper HTML tables | | |
| Bold/italic | Formatting renders correctly | | |
| Code blocks | Syntax-highlighted with copy button | | |
| Copy button works | Click copy icon on a code block — copies to clipboard | | |

### 5.9 Long Conversation — Context Window

1. Have a conversation with 25+ messages
2. Continue chatting

| Check | Expected | P/F | Notes |
|-------|----------|-----|-------|
| AI stays coherent | Responses still reference earlier context | | |
| Full history in UI | Can scroll back to see all 25+ messages | | |
| No performance issues | UI remains responsive | | |

---

## Results Summary

| Phase | Tests | Pass | Fail | Notes |
|-------|-------|------|------|-------|
| Phase 1: Infrastructure | 1.1 – 1.6 | | | |
| Phase 2: Onboarding | 2.1 – 2.4 | | | |
| Phase 3: Core Chat | 3.1 – 3.9 | | | |
| Phase 4: Advanced | 4.1 – 4.7 | | | |
| Phase 5: Edge Cases | 5.1 – 5.9 | | | |
| **Total** | **36 test sections** | | | |
