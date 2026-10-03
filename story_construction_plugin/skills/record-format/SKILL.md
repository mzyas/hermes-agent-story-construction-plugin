---
name: record-format
description: What goes in the text of a proposal for a chapter, character, world entry or note, and how to word the edits.
---

# Record format

Read this before writing the text of a proposal: `new_text` and `content` in
`story.propose_edit` and `story.propose_new`, and the name in
`story.propose_rename`.

## The text is only the record

- Write only what belongs in the record: no greeting, no "here is", no
  explanation, no closing remark ("hope this helps", "let me know"), no code
  fence, no frontmatter (`---` block), and no heading that repeats the
  record's title or name. Say everything else in your chat reply.
- The title or name is a separate field. Never repeat it inside the text.
- The review shows an introduction, a closing remark or a repeated heading in
  red and removes a wrapping code fence, but do not rely on that: the person
  has to read what you wrote.

## Match what is already there

- Write in the language the person is writing in and the project's existing
  text uses. A new project's default titles ("第一章", "Chapter 1") say nothing
  about the language of the story. Keep the layout, headings and voice
  of the existing records of the same kind. When unsure, read one first
  (`story.get_record`, or `story.get_chapter`).
- A chapter is story prose only. A character, a world entry or a note is the
  record's own text, not a chat message about it.
- Do not add anything the person did not ask for.

## Wording the edits

- Prefer small `replace` edits. Copy `old_text` exactly from what you read,
  including punctuation: full-width CJK punctuation is not the same as
  half-width. Add enough surrounding text for it to appear exactly once, or the
  whole proposal is rejected.
- `insert_after` / `insert_before` put `new_text` next to `anchor_text`.
  `append` / `prepend` add a new paragraph at the end / start.
- Use `rewrite` only when most of the text changes. It must be the only edit.
- Several changes to one record go in one proposal, as several edits.
- Pass the `version` you read as `base_version`; if the record changed since,
  read it again and propose again.

## Names

- `new_title` is only the name. A name another record already has gets a
  number after it when it is written (`林远 (2)`); a `name_in_use` warning says
  so.
- To change the text and the name, make two proposals: `story.propose_edit`
  and `story.propose_rename`.
