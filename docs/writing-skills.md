# Writing skills

Each skill is a directory containing `SKILL.md` with YAML frontmatter, optional
references, templates, assets, and scripts. The frontmatter must include
`name` and `description`. Keep instructions focused on one repeatable editing
workflow and state the expected inputs and outputs.

Uploaded archives are rejected when they contain symlinks, absolute paths,
`..` path traversal, oversized files, or no `SKILL.md`. Script-bearing skills
are stored disabled until the user explicitly approves their scripts. The
agent prompt receives only a compact skill index; the full body is loaded when
the skill is selected.

Use project memory for brand facts and standing instructions. Do not copy
source footage into a skill or embed provider credentials in scripts.
