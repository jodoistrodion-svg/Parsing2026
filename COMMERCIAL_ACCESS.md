# Commercial access / licensing

## What is implemented

Parsing2026 now supports a controlled paid-access workflow without giving customers the source code:

1. Owner opens **🔑 Коды доступа**.
2. Owner presses **➕ Создать код**.
3. The bot generates a cryptographically random one-time code.
4. The plaintext code is shown to the owner once. Only its SHA-256 hash is stored in SQLite.
5. Owner sends the code to the buyer after confirming payment.
6. Buyer opens the bot and chooses **🔑 Ввести код доступа**.
7. Redemption atomically binds the code to the buyer's Telegram user ID.
8. The same code cannot be redeemed by another user.
9. A user cannot redeem another code while an active license already exists.
10. Owner can view license statistics and revoke active access by Telegram ID.

## Important distinction

The licensing layer controls access to the bot. It does **not** process payments.

For manual sales, the operational flow is:

payment confirmed by owner -> generate code -> send code -> buyer redeems code

If payments are later accepted **inside Telegram** for digital goods/services, implement Telegram Stars (`XTR`) payment handling and store successful payment charge IDs before delivering access. Telegram's current documentation also calls for accessible terms and customer support.

## Before commercial launch

- Obtain and configure a valid LZT API key. The current V3 runtime intentionally fails closed for missing LZT credentials; without an LZT key, the Telegram shell can run but the LZT-dependent product functionality cannot be sold as operational.
- Keep `AUTOBUY_MODE=dry-run` until the LZT API path has been tested end-to-end.
- Move the bot from the development workstation to a stable always-on host.
- Back up `bot_data.sqlite` and verify restoration.
- Keep `.env`, SQLite files and logs out of Git.
- Enable 2FA on the Telegram account controlling the bot.
- Publish real Terms of Service and a customer support contact before taking payments.
- Decide the commercial entitlement model: lifetime, fixed-term, or subscription. The current implementation is lifetime until manually revoked.
- Verify that selling/reselling this service is permitted by the LZT/API provider's current terms. This repository does not establish that permission.

## Security properties

- Access codes are generated with Python's `secrets` module.
- Codes are normalized before validation.
- Only SHA-256 hashes are persisted; plaintext codes are not stored.
- Redemption uses a SQLite `BEGIN IMMEDIATE` transaction to make concurrent redemption single-winner.
- A redeemed code stores the Telegram user ID and redemption timestamp.
- Revoked licenses remain recorded for auditability.
- Owner-only license management is enforced by the existing `OWNER_IDS` access control.

## Recovery

The SQLite database is part of the license state. Losing the database loses the mapping between issued codes and Telegram IDs. Back up the database before commercial operation and after meaningful sales batches.

## Not yet automated

The repository does not automatically:

- verify external payment;
- issue a code after payment;
- calculate prices;
- manage recurring billing;
- expire licenses by date;
- generate invoices.

Those are separate product/payment features and should be implemented only after the underlying LZT service path is operational.
