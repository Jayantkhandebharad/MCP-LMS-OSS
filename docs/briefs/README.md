# Blog briefs

**The actual blog posts do NOT live in this repo.** They live in the portfolio:

- Series registry: `portfolio/src/content/blog.ts` (series slug `mcp`)
- Post bodies: `portfolio/src/content/blog/mcp/*.tsx` (currently "Coming Soon" placeholders)

This directory holds the **brief** for each post — the raw material captured *while building*, handed to the blog writer when a phase completes. The goal of the series is to teach MCP in real depth, so the brief's job is to preserve the things that are impossible to reconstruct after the fact: the actual errors, the wrong turns, the "why is Moodle like this" moments.

## One brief per phase

| Brief | Feeds portfolio post |
|---|---|
| `phase-3-building-an-mcp-server.md` | `building-an-mcp-server.tsx` |
| `phase-4-rbac-in-mcp.md` | `rbac-in-mcp.tsx` |
| `phase-5-mcp-auth-done-right.md` | `mcp-auth-done-right.tsx` |
| `phase-6-securing-an-mcp-server.md` | `securing-an-mcp-server.tsx` |
| `phase-7-deploying-mcp-on-gcp.md` | `deploying-mcp-on-gcp.tsx` |

(Phases 1–2 don't get their own posts; their gotchas fold into the Phase 3 brief.)

## Brief template

```markdown
# Brief: <post title>  (Phase N)

## One-line thesis
What should the reader be able to do/explain after reading?

## Concepts to teach (in depth — this is the point of the series)
- concept → where it shows up in our code (file:line or commit)

## Real issues we hit (capture these THE DAY they happen)
- symptom → root cause → fix → what the docs didn't tell us

## Code moments worth showing
- commit hashes / files that make good snippets

## Diagrams needed
- what to draw

## Interview-question angles
- questions this post should equip the reader to answer
```
