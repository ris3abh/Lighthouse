# 2. Distribution and CLI name: `lighthouse-gc`

Date: 2026-10-06 · Status: accepted

## Context
"lighthouse" collides on PyPI and with Google's `lighthouse` npm CLI on users' PATH.

## Decision
Ship as `lighthouse-gc` (PyPI and CLI command); the import package is `lighthouse_gc`. The project is still
called Lighthouse in prose.
