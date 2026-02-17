# Claude Code Guidelines

## Database Queries

**NEVER directly edit `api/queries.py`.** This file is auto-generated from the `.edgeql` files in the `queries/` directory.

To add or modify queries:
1. Create or edit the `.edgeql` file in `queries/`
2. Run `npm run generate:queries` to regenerate `api/queries.py`

The generation command runs: `uv run gel-py --target async --file api/queries.py`

When needed, the developer will run this command for you in their dev environment.