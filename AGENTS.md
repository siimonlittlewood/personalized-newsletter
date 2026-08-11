# Project instructions

## Secrets and sensitive files

- No agent may read, print, search, parse, summarize, or otherwise inspect the contents of any actual environment file, including `.env`, `.env.local`, `.env.*.local`, or similarly named environment files that may contain real values.
- No agent may scan or inspect files that are highly likely to contain secrets, credentials, authentication tokens, private keys, session data, or other sensitive values. This includes credential stores, key files, authentication databases, and secret-manager exports.
- Agents may check whether a sensitive file exists and may inspect non-content metadata when necessary, but must not read its contents.
- Sanitized example and template files intended for documentation are allowed, including `.env.example`, `.env.sample`, and equivalent example files.
- If completing a task appears to require reading a prohibited file, stop and ask the user for a sanitized excerpt or an alternative approach. User permission does not override this project's prohibition on agents reading actual secret-bearing files.
