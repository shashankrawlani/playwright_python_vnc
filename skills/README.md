# Skills Bundle

This directory contains installable skills that ship with the repository and are
safe to share without secrets or personal data.

## Install

From this repository root, a user can install the bundle with the open skills
CLI:

```bash
npx skills add ./skills --skill pyplayvnc --copy -y
```

If the caller wants the skill copied into a global agent directory instead of
the current project, they can add `-g`.

## Contents

- `pyplayvnc` - operating the PyPlayVNC persona browser, VNC workflow, and MCP sidecars
