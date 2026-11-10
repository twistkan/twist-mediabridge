# Repository scope

This repository starts with a snapshot of the current source on 4 November 2026.
Historical failed builds, old installers, backup source trees, virtual environments,
runtime caches, private records, logs and signing credentials are omitted.
Original working folders on the development PC are preserved.

Windows downloads belong in GitHub Releases, separately from source control.
Dependencies and external tools must be restored before building.
No open-source license has been granted to this application's own source.
Third-party notices and licenses retain their existing terms.

## Restoring build tools

Install the packages in `requirements-media.txt` and PyInstaller in a Python
environment. The original build script expects packages in `vendor/`; install
with `python -m pip install -r requirements-media.txt --target vendor`.
Restore Android Platform Tools to `tools/android/platform-tools/`, aapt2 and its
NOTICE to `tools/aapt2/`, before
running `build-media.ps1`. The APK build additionally expects a JDK under
`tools/java/`, Android API 35 android.jar under `tools/sdk/platform/android-35/`,
and Android build tools under `tools/sdk/build-tools/android-15/`.
Third-party notices are included in `licenses/` and embedded by the desktop build. Signing credentials are intentionally omitted. New keys cannot update an
existing phone installation signed with the original key; retain the original
signing directory securely outside GitHub.


## Version 1.16

Adds a Send to phone page with native Windows file drops, optional automatic sending, manual queueing, multiple-phone selection and verified shared-storage writes. Existing connections, media, contacts, APK installation and backup workflows are retained. Release binaries remain in GitHub Releases. Local data, caches, signing material and historical builds are excluded.
