# Companion sound credits

This pack contains short edits of recordings and natural foley. Calls are
recordings for dog, cat, bird, owl and dolphin. Rabbit clips are recorded rabbit
movement. Bat uses wing-flutter foley; turtle uses gentle footstep foley; fish
uses water-bubble foley. Plants have designed movement textures rather than
purported plant vocalizations.

`manifest.json` records every source, author, original URL, pinned download,
source checksum, excerpt, filter and output checksum. Sources were retrieved
October 23, 2026. Some mirrors have already edited their masters; the manifest's
intervals refer to those pinned masters.

| Recordings | Creator | License |
| --- | --- | --- |
| Cat, dog and owl calls | Joseph SARDIN / BigSoundBank | CC0 1.0 |
| White-crowned Sparrow Chirp | Zott820 | CC0 1.0 |
| Cat purr.wav | rareguy27 | CC0 1.0 |
| Cat eating dry-food (croquettes) | Sadiquecat | CC0 1.0 |
| Dolphins underwater in Caribbean Sea | felix.blume | CC0 1.0 |
| Leaves Rustling | Eric Norcross | CC0 1.0 |
| Organic Wooshes; Bottle Plops | Ben Burnes / Abstraction | CC0 1.0 |
| Grass and wood footsteps; light wood impact | Kenney | CC0 1.0 |
| Sounds of a rollicking House Rabbit | Fiver, der Hellseher | CC BY-SA 4.0 |

CC0 recordings and their edits are distributed under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

**Rabbit attribution:** `rabbit-1.mp3` and `rabbit-2.mp3` are adapted from
[Sounds of a rollicking House Rabbit](https://commons.wikimedia.org/wiki/File:Sounds_of_a_rollicking_House_Rabbit.flac)
by Fiver, der Hellseher, under
[Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
Office Connect trimmed, filtered, mixed to mono, balanced the volume, applied
fades and encoded these excerpts as MP3. These two adapted audio files remain
under CC BY-SA 4.0. That license applies to those files, independently of the
application's code and the CC0 audio.

## Rebuilding

Run `python scripts/build_avatar_audio.py --source-dir /tmp/avatar-audio-input`.
The script downloads missing sources from pinned URLs, verifies their checksums,
and uses ffmpeg to regenerate the pack and output checksums. FFmpeg's encoder
version may change output bytes. The build uses no paid service or API key.

## Playback

The pack is served locally and fetched only after opting into sound. Only the
requested clip is decoded and cached in memory. The existing service worker
caches successful public static responses as they are used; already fetched
clips can play offline in an open page. The PWA does not cache personal pages.
Recorded voice playback fails quietly if a clip cannot load or decode.

Cat voice clips preserve the complete meow ending: `cat-meow-1.mp3` is one
full meow and `cat-meow-2.mp3` contains two calls. Petting still uses a purr.
