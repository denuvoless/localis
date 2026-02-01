# localis
signal-based neighborhood watchdog verification bot.

> **⚠️ note:** this is a hobby project and a proof of concept. it is not **currently** intended for production use or public deployment.

## overview
localis acts as a gatekeeper for Signal groups. it interfaces with `signal-cli` to automate user onboarding by:

* listening for incoming "join" commands.
* verifying the sender's area code against an allowlist.
* routing users to either a **Primary Group** (verified locals) or a **Guest Group** (non-locals).
* handling users with hidden phone numbers (UUIDs) by requesting manual verification (contacting the group admin) or setting changes.
