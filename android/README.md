# Parsing2026 on Android / Termux

This branch adds an Android deployment layer around the existing Parsing2026 runtime. The application core is not rewritten for Android; the deployment is adapted so the same production code runs inside Termux with Android-native persistence, service supervision and boot startup.

## Target device

Current target: realme C35, Android 13, realme UI T Edition, 4 GB physical RAM, 128 GB storage.

The bot is lightweight enough for this class of device. The important constraints are Android background execution, battery management, networking and boot recovery rather than CPU capacity.

## Architecture

    Android 13
        |
        +-- Termux
        |     +-- Python + venv (--system-site-packages)
        |     +-- Parsing2026
        |     +-- SQLite in $HOME/.local/share/parsing2026
        |     +-- termux-services / runit
        |     +-- Termux:Boot
        |
        +-- Telegram API
        +-- LZT API

termux-services supervises the Python process and restarts it if it exits. Termux:Boot starts the enabled service supervisor after Android boot. A Termux wake lock is acquired at boot because the bot is intended to run continuously.

## Why Android has a separate requirements file

Termux provides a native python-cryptography package. Android requirements therefore install the runtime dependencies through pip and deliberately do not reinstall cryptography from PyPI. This avoids forcing a Rust build on the phone.

## First installation

Install Termux from one source and keep all Termux add-ons on the same source/signing family. The official Termux project documents F-Droid and GitHub releases; Termux:Boot must use a compatible signing source.

Then in Termux, from the cloned repository:

    bash android/bootstrap.sh
    bash android/install-service.sh

Install and open Termux:Boot once, then run:

    bash android/install-boot.sh

Check:

    bash android/status.sh

The initial configuration always uses:

    AUTOBUY_MODE=dry-run

Do not enable live purchasing just because the Android deployment works. The existing project audit still requires controlled live-runtime validation.

## Service commands

Start:

    bash android/start.sh

Stop:

    bash android/stop.sh

Status + recent logs:

    bash android/status.sh

Service log:

    $PREFIX/var/log/sv/parsing2026/current

## Data and secrets

Persistent Android data lives under:

    $HOME/.local/share/parsing2026/

The repository .env contains the Telegram bot token and Fernet encryption key, so it is ignored by Git. File permissions are set to owner-only during bootstrap. Do not upload .env or database files to GitHub.

The generated Fernet key is required to decrypt stored customer LZT credentials. Losing it makes those credentials unrecoverable.

## Backup

After termux-setup-storage has been granted, run:

    bash android/backup.sh

Backups are written to:

    ~/storage/downloads/parsing2026-backups/

The database backup uses SQLite's backup API instead of copying a live WAL file.

## realme UI T Edition

realme documents that background operation may require allowing foreground/background activity and auto-launch under App battery management. On T Edition, the generic recent-task app-lock mechanism is documented as unsupported, so do not rely on that as the primary keep-alive mechanism.

Recommended device-side settings before 24/7 use:

1. Disable Power saving mode.
2. Allow Termux to run in the background / unrestricted battery mode if exposed.
3. Allow Termux auto-launch if exposed by the firmware.
4. Keep Termux and Termux:Boot installed from the same source.
5. Keep the phone on reliable Wi-Fi or stable mobile data.
6. Keep the phone powered continuously for server use.

## Diagnostics

Run these commands when reporting an Android problem:

    termux-info
    uname -m
    python --version
    curl -I https://api.telegram.org
    python -c "import aiohttp; print(aiohttp.__version__)"
    python -c "import cryptography; print(cryptography.__version__)"
    bash android/status.sh

Debug the actual error rather than repeatedly restarting the process blindly.
