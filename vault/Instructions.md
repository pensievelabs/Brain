---
date: 2026-03-08
tags:
  - "#resource"
  - "#meta"
---
# [[Instructions]]

## PARA Methodology
This vault operates on the PARA method for personal knowledge management:
1. **[[Projects]]**: Active builds or goals with a deadline → `1-Projects/`
2. **[[Areas]]**: Spheres of ongoing responsibility → `2-Areas/`
3. **[[Resources]]**: Topics of interest and passive research → `3-Resources/`
4. **[[Archives]]**: Completed or inactive items → `4-Archives/`

## AI Interactions ([[BrainBot]])

### Propose → Confirm → Act
- BrainBot classifies every message by **semantic intent** (shower thought, project, query, etc.)
- For vault mutations, it **proposes** the action first and waits for confirmation
- Reply "yes" to confirm, or describe a correction in natural language
- Queries and `/coach`/`/explore` commands execute immediately

### Intent Types
| Intent | Where it goes |
|---|---|
| Shower thought | `3-Resources/` |
| New project | `1-Projects/` |
| Project update | Appends to existing project |
| Area update | `2-Areas/` |
| Action item | Related file or `Inbox/` |
| Archive | `4-Archives/` |

### Formatting
- Every note requires YAML frontmatter with `date` and `tags`
- Use `## Next Actions` with `- [ ]` for task tracking
- Proactively use `[[WikiLinks]]` for entities and concepts
- BrainBot automatically promotes `#resource` → `#project` when concrete actions are taken (tag evolution)

## Workflow
- Use templates found in each directory to maintain structural integrity
- Direct thoughts to the `Inbox/` for later processing
- BrainBot searches the vault before creating new files to avoid duplicates
