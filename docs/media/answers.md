# Real answers from GitLore

Recorded with `scripts/capture_media.py` on the demo project, Qwen3 1.7B — recommended (1.1 GB), CPU only.

## Why did we switch login to JWT?

> The switch to JWT tokens was motivated by the need to handle multiple instances of the application behind a load balancer. Server-side sessions would cause a user to be logged out on the other instance, as each instance only knew its own sessions. Signed JWT tokens are stateless, meaning any instance can verify them without shared storage.
> 
> This change was made [04ad8dd] by Leo Martin to address the issue of session consistency across multiple instances.

## Why was the CSV export reverted?

> The CSV export was reverted because the file was not opened with newline="", which caused blank lines between rows on Windows. This issue was identified in the revert commit [9758330], where the export function was reverted to a state where the file was not properly configured for newline handling. The revert was made to address the problem, and the fix was later implemented in the commit [11fef00], where the export function was updated to use newline="" to ensure proper CSV formatting across all platforms.

## List the security fixes.

> Security: refresh() must reject expired tokens [bd8949f]
> This commit addresses a vulnerability where refresh() could reuse a cached decode that skipped the expiry check, allowing an expired token to be refreshed forever.
> Security: rate-limit failed logins [457216d]
> A new rate-limiting mechanism is added to prevent brute-force attacks by limiting failed login attempts per user within a 15-minute window.
> Security: Fix SQL injection in search [e65b4c1]
> The search() function now uses parameterized queries to prevent SQL injection, avoiding vulnerable f-string constructions like ' OR 1=1 --'.
> Security: Hash passwords with PBKDF2 instead of plain SHA-256 [42a66f5]
> Passwords are hashed using PBKDF2 with a per-user salt and 600,000 iterations to mitigate brute-force risks if user data is exposed.

## What has Priya Nair worked on?

> Priya Nair has worked on the following changes:
> 
> Refactored error handling in the CLI [eafadef] by adding a friendly function to return a more user-friendly error message.
> Fixed a crash when a due date was malformed [c60eb5e] by implementing a parse_due function that converts dates from ISO format to Python dates.
> Improved security by ensuring the refresh() function re-validates tokens, preventing expired tokens from being refreshed indefinitely [bd8949f].
> Changed how unknown tasks are handled, returning a 404 instead of a 500 error [43d3d68].
> Extracted date parsing into a helper function [054de0f] to improve code organization.
> Optimized performance by avoiding re-loading the config on every command [4346cd8].
> Clarified installation steps in the README [f39e1c8].
> Explained recurring task rules in the usage documentation [820c775].
> Pinned the Python version for local development [a0595c5].
> Added rate limiting to prevent excessive failed logins [457216d].

## Why did we add Kubernetes support?

> The question asks why we added Kubernetes support, but none of the provided commits mention Kubernetes or any related changes. Therefore, I cannot answer this question based on the given commits.
