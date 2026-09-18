# Security

## Secrets

Never commit .env, Telegram tokens, LZT keys, secret answers or database files.

The configuration loader accepts several legacy variable names for migration, but the preferred names are API_TOKEN, OWNER_ID and LZT_API_KEY.

## Safe operations

Autobuy is latency-sensitive, so the runtime uses bounded concurrency and explicit terminal/error classification. Queue saturation rejects new work rather than silently discarding existing jobs.

## Incident response

If a Telegram or LZT credential is exposed, revoke and rotate it at the provider before resuming the bot.

## Reports

For a private vulnerability report, use the repository owner's GitHub security/contact channel rather than opening a public issue.
