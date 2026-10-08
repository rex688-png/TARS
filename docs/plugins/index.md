# TARS plugins and local providers

The six official behavior plugins are bundled with TARS: **TARS Explorer, TARS
Navigator, TARS Galaxy, TARS Chatter, TARS Expedition, and TARS Observatory
Bridge**. They work together as one assistant. The verified source revision and
file hashes are recorded in `vendor/tars-plugins/provenance.json`. TARS does not
scan arbitrary plugin folders in its product profile.

Local providers are separate, optional packages. The controlled provider setup
can install **Parakeet STT**, **Pocket-TTS 0.0.17-tarsfix**, **Supertonic TTS**,
and **Gemma Embedding** after an explicit download request. None is bundled in
the base MSI or portable package. Provider archives are verified before being
installed under `%APPDATA%\TARS\providers`; restart TARS after installation.
Settings and credentials live in the TARS user profile, not in provider
package folders. See [provider setup](../tars-alpha-provider-setup.md) and
[installation](../tars-installation.md).

The inherited [plugin development guide](Development.md) describes the upstream
COVAS:NEXT API. It is reference material, not instructions to install arbitrary
plugins into the controlled TARS product profile.
