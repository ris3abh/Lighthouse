# The Area O1 capture extension

Some official sites (uscis.gov, travel.state.gov) block automated reading, so Area O1 can't refresh them by itself.
The capture extension fixes that without any chores: when **you** visit one of the pages your vault lists, it saves
that page to Area O1 on your computer. It never opens, reloads or fetches pages on its own, and it only talks to
Area O1 at `http://127.0.0.1` ([ADR 0011](adr/0011-vault-without-babysitting.md)).

## Install (Chrome, Edge, Brave)

1. Run `areao1 extension` to see where the extension folder is (or unzip `areao1-capture-<version>.zip`).
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and choose that folder.
3. In Area O1, open **Knowledge > Browser extension > Get a pairing code**. Click the extension's icon, check the
   Area O1 address (default `http://127.0.0.1:7777`), type the code and press **Pair**.

The popup then says how many official pages it watches. Visit one (for example the Form I-129 page) and the
extension's badge shows **OK**: the page is in your vault, checked now.

## What it can and can't do

- Its permissions are `storage`, `scripting`, and the vault's official domains plus `127.0.0.1`. It reads a page
  only when its address matches one of the vault's sources exactly.
- It sends the page's HTML to your local Area O1 with a capture token (only its hash is stored in Area O1). Pairing
  again or **Unpair** replaces it.
- **Share captures with the community library** (off by default) prepares captures of public U.S. government pages
  for the community snapshot library; nothing is uploaded automatically.
