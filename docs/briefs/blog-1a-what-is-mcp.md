# Brief: What is MCP, Actually?  (Blog #1a — new intro post, split from Blog #1)

> Created 2026-07-13 after reviewing the first draft of Blog #1: it assumed too much.
> This post carries ALL the MCP theory so the build post can stay a build post.

## Audience — this defines everything

A third-year engineering student. They have used ChatGPT/Claude, written some Python,
maybe touched an API. They have NEVER heard of MCP, JSON-RPC, or an LMS. Rules:

- Define every term the sentence it first appears. No exceptions.
- Short sentences. One idea per sentence. No stacked jargon.
- Analogy before abstraction, always.
- If a paragraph doesn't serve the objective, cut it.

## One-line objective (state it AT THE TOP of the post)

"By the end of this post you'll know what MCP is, why it exists, and what its three
building blocks do — enough to read any MCP server's code and know where to look."

## Structure (in order)

1. **The problem, concretely.** AI assistants are smart but sealed off: Claude can
   reason about your courses but can't SEE your university's course site. Every app
   that wants AI needs a custom integration to every system. N apps × M systems =
   N×M integrations. Show the pain simply.
2. **What MCP is.** Model Context Protocol: an open standard (Anthropic, Nov 2024,
   now industry-wide) for connecting AI applications to external systems. The USB-C
   analogy: one port, any device. Define protocol itself in one line ("an agreed
   format for messages between two programs").
3. **The three players.** Host (the AI app, e.g. Claude Desktop), client (the
   connector inside it), server (the program exposing a system). Everyday example
   thread: "your university's Moodle" — which conveniently sets up the next post.
4. **The three primitives, gently.** Tools / resources / prompts with the
   who-initiates framing (model / application / user), one everyday example each.
   The table from the current draft can move here.
5. **How they talk, in one paragraph.** JSON-RPC messages; two transports: stdio
   (client launches the server on your machine) vs Streamable HTTP (server runs
   remotely). One sentence on sampling as a teaser for later posts.
6. **See it for 60 seconds.** Screenshots: `phase3-tools-list.png` (an MCP client
   showing a server's tools) + `phase3-claude-demo.png` (Claude taking a quiz through
   one). One paragraph: "this is a server I built; next post builds it from zero."
7. **Recap + MCQ quiz** (3 questions max, reuse the seeded quiz's questions — they're
   exactly this material).

## What does NOT belong here

stdout/stderr discipline, FastMCP, docstrings, adapter layers, Moodle API pain,
Docker, seeding — ALL of that is Blog #1b (the build). If it mentions code, it's
in the wrong post. Keep this one readable in ~8 minutes.

## Registry notes (portfolio repo)

New entry in `src/content/blog.ts` mcp series, BEFORE building-an-mcp-server:
slug `what-is-mcp`, title "What is MCP, Actually?", lessonType Concept,
phase label "Foundations", no prerequisites. building-an-mcp-server gets
`prerequisites: 'What is MCP, Actually?'`.
