# Media preview components

DeviceBridge Media uses Pillow 13.0.0, pillow-heif 1.8.1 (including libheif and its bundled codec dependencies), and imageio-ffmpeg 0.6.0. Their upstream notices are included in `release/licenses` alongside the executable.

The imageio-ffmpeg Windows wheel supplies FFmpeg 7.1 for decoding and preview playback. Its binary is built with GPL components. Upstream FFmpeg license and source information: https://ffmpeg.org/legal.html and https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz . Binary/build provenance: https://github.com/imageio/imageio-ffmpeg .

Pillow: https://python-pillow.org/ . pillow-heif: https://github.com/bigcat88/pillow_heif . imageio-ffmpeg: https://github.com/imageio/imageio-ffmpeg .

No Wondershare code, graphics or media are included. Test screenshots use generated fixture images, not user photos or assets shipped in the application.

AAPT2 (Google Android tools), downloaded from the official Google Maven repository. Bundled NOTICE under licenses/aapt2. Used to read app display labels from APK manifest/resources; documentation: https://developer.android.com/tools/aapt2

Wi-Fi discovery and QR pairing: python-zeroconf 0.151.5 (LGPL-2.1-or-later, https://github.com/python-zeroconf/python-zeroconf), ifaddr 0.2.0 (MIT, https://github.com/p-st/ifaddr), and qrcode 8.2 (BSD, https://github.com/lincolnloop/python-qrcode). Upstream license texts are bundled under licenses/. QR generation is local and does not upload pairing credentials.

Companion encrypted local sessions: cryptography 50.0.2 (Apache-2.0/BSD, bundled OpenSSL), cffi 2.1.1 and pycparser 3.12. Upstream licenses are bundled under licenses/. https://cryptography.io/ . Phone QR decoding: ZXing Core 3.5.3 (Apache-2.0), https://github.com/zxing/zxing . Its license is embedded in the APK and desktop notices.

