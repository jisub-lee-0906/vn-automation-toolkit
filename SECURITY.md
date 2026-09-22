# Security boundaries

## Trusted local CLI configuration

This repository contains developer automation. Explicit CLI runner configuration is trusted local operator input, not a network service interface. Run only reviewed commands and workflows. Do not expose runner override options through a web/API service or accept them from untrusted project files.

## Loopback services

Loopback endpoints are local integration settings, not credentials and not remotely reachable by themselves. Bind services to loopback unless deliberate authenticated network deployment is designed and reviewed.

## Private artifacts

Local QA evidence, backups, generation logs, machine-specific paths, screenshots, contact sheets, and media require release review. Keep private operational artifacts out of public release allowlists. Inspect media visually and aurally before publication.

## Reporting

Report suspected credentials or unsafe publication artifacts privately. Do not include secret values in reports or issues.
