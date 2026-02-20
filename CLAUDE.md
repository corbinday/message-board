# Claude Code Guidelines

## Database Queries
* **NEVER directly edit `api/queries.py`.** This file is auto-generated from the `.edgeql` files in the `queries/` directory. To add or modify queries simply create or edit the `.edgeql` file in `queries/`. The developer will run the command `npm run generate:queries` command for you in their dev environment.
* **Never** try to run database migrations after editing default.gel or any of the other .gel files.

## CSP and JavaScript
Mind the CSP when adding JavaScript, try to put as much of the JS into script files as possible (so the sha384 hash is automatically generated) as possible, rather than inline scripting. When editing a feature that has inline scripting, try to move into an existing js file if that makes sense, a new one if not, and finally leaving the inline script with a nonce as a last resort.