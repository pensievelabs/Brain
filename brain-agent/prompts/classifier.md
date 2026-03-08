# Intent Classifier Prompt

Classify every incoming message into exactly one of these intents:

| Intent | Signals | PARA Tag | Target Directory |
|---|---|---|---|
| `shower_thought` | Casual, abstract, philosophical, no deadline or action implied. Observations, musings, "I think…", metaphors. | `#resource` | `3-Resources/` |
| `project_creation` | Concrete goal with a deadline or build-target. "I'm going to build…", "Starting a new…", "Goal: …" | `#project` | `1-Projects/` |
| `project_update` | References an existing project by name or context. Progress report, blocker, status change. "Ordered the parts for…", "Made progress on…" | `#project` | `1-Projects/` |
| `area_update` | Ongoing responsibility with no end date. Career, health, finances, relationships. "My portfolio is…", "Need to stay on top of…" | `#area` | `2-Areas/` |
| `action_item` | Explicit task. "I need to…", "Remind me to…", "Don't forget to…", imperative verb. | Contextual | Append to related file, or `Inbox/` |
| `archival` | Completion or deactivation. "Done with…", "Finished…", "No longer pursuing…" | `#archive` | `4-Archives/` |
| `query` | Question, retrieval request. "What did I write about…", "Find my note on…", "?" | — | No mutation |
| `correction` | Modifies a previous proposal. "No, put it in…", "Change that to…", "Actually…" | — | Re-propose |

**When ambiguous:** Ask the user: "Is this a new project, a thought to file, or something else?"
