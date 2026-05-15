# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please **do not**
open a public GitHub issue. Public disclosure before maintainers have had a
chance to review and respond may put users at risk.

**Preferred method:** Use GitHub's private vulnerability reporting feature:
[Report a vulnerability](https://github.com/ikentrock/deskpet/security/advisories/new)

If private reporting is unavailable, contact the maintainer directly through
GitHub: [@ikentrock](https://github.com/ikentrock)

Please include:
- A description of the vulnerability and its potential impact
- Steps to reproduce the issue
- Any relevant environment details (macOS version, Python version, etc.)

Maintainers will acknowledge receipt and aim to respond within a reasonable
timeframe. Once a fix is ready, a coordinated disclosure will be arranged.

## Pet Bundle Safety

This application loads `.codex-pet.zip` pet bundle files at runtime. These
bundles are ZIP archives that may contain Python-readable image and JSON files.

**Users should only load pet bundles from sources they trust.**

- Third-party pet bundles have not been reviewed or verified by the maintainers
  of this project.
- Do not load pet bundles from unknown or untrusted sources.
- The maintainers of this project are not responsible for the content, safety,
  or licensing of third-party pet bundle files.

## Scope

This security policy applies to the source code in this repository. It does
not cover third-party dependencies, external pet bundle content, or systems
outside the scope of this project.
