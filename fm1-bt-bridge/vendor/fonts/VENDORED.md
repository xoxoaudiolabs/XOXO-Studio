# Vendored: the XOXO fonts

The fonts of the XOXO Audio Labs website, so the Studio's touchscreen and the web look alike. Copied unchanged
from [google/fonts](https://github.com/google/fonts) (`main`, 2026-10-31):

- `Anton-Regular.ttf` (`ofl/anton/`): the big type (the tempo, REC / START / TAP, the boot screen).
  Copyright 2020 The Anton Project Authors, under the SIL Open Font License 1.1 (`Anton-OFL.txt`).
- `IBMPlexMono-Medium.ttf`, `IBMPlexMono-SemiBold.ttf` (`ofl/ibmplexmono/`): everything else.
  Copyright 2017 IBM Corp., with Reserved Font Name "Plex", under the SIL Open Font License 1.1
  (`IBMPlexMono-OFL.txt`).

`xoxostyle.py` draws with them through Pillow (FreeType). They replace the Terminus pixel font the Studio used
while it looked like SLOOP.
