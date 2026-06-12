# Idea: Skills Management UI

## Problem

Cortex currently deploys skills to projects via CLI setup scripts and extension sync, but there's no UI for users to browse, manage, or assign skills to projects. Users can't see what skills are available, create skill groups, or customize which skills get deployed.

## Concept

Add a **Skills Management** section to the Cortex UI left navigation. This section would function similarly to the Knowledge Base section — card-based browsing with management capabilities.

## Core Features

### Skills Library
- Card-based view of all skills Cortex has stored (similar to knowledge base cards)
- Each card shows: skill name, description, version, trigger conditions
- Ability to view full skill content
- Add new skills directly through the UI (paste SKILL.md content or upload)

### Skill Groups
- Create named groups of skills (e.g., "FastAPI Development", "Frontend React", "DevOps")
- Drag/drop or checkbox-based assignment of skills to groups
- One group designated as the **Default Skill Group** — automatically deployed to any new project connected to Cortex
- Users can extend the default group with additional skills per-project

### Project Assignment
- From the project detail view, see which skill groups/individual skills are assigned
- Override the default group: add extra skills or remove ones that aren't relevant
- Per-project skill customization without affecting the default group

### Default Skill Group
- Ships with a curated set of core skills (e.g., cortex-memory, postman-integration, etc.)
- Users can modify which skills are in the default group
- New projects automatically receive the default group's skills during setup
- Clear indicator of which group is the default, with ability to change it

## Integration Points

- **Setup scripts** (`cortexSetup.sh` / `.bat`) — pull skill assignments from Cortex when bootstrapping a project
- **Extension sync** (`/cortex-extension-sync`) — respect project-level skill assignments
- **Skill registry** — backend already tracks extensions; extend to support grouping and defaults

## Status

Idea only — not yet brainstormed or specced.
