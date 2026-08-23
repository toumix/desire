# TODO — sweep.py should diagnose the capability gate, not traceback

The scheduled prompt, verbatim:

> Follow toumix/desire/EVENING.md

- [x] Turn a repo-scoped 403 into one clear diagnosis and exit 2, so a turn cannot read a crashed
  sweep as a clean one and does not re-derive
  [desire#95](https://github.com/toumix/desire/issues/95) from scratch a sixth time.
- [x] Record on desire#95 what this session measured: the gate is now the steady state, reaction
  *counts* are readable over MCP, and GraphQL is gated too.
