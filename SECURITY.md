# Security policy

## This repository contains no credentials

This is a public edition of a private system. Hostnames, IP addresses, SSH
credentials, API tokens and machine identifiers have been removed. Example
configuration uses placeholders only.

If you find a secret in this repository, please report it immediately:

- Email: matsumotoinla@gmail.com
- Or open a private security advisory on GitHub

Do not open a public issue for a leaked secret.

## Reporting a vulnerability

Same contact as above. Please include reproduction steps and the affected file.

## Scope

This repository is a portfolio / reference implementation, not a production
service. There is no hosted endpoint to test against.

## If you fork this

`.gitignore` excludes `.env`, `secrets.env`, `*.pem` and `*.key` by default.
Keep it that way, and never paste tokens into documentation or commit messages.
