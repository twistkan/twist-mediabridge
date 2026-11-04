# Twist MediaBridge — complete build prompt

Copy the prompt below into a coding agent with access to a Windows development workspace. It specifies the complete app, including the requested **Powered by Tweest** UI credit. A single prompt defines the project; actual implementation, testing and hardware verification still require work.

---

You are an experienced Windows desktop and Android engineer. Build a complete, original application called **Twist MediaBridge**. Implement working source, tests, documentation and a single executable. Continue through implementation, bug fixes and packaged verification; do not stop at a plan or visual mockup.

## 1. Identity and product scope

- Name: **Twist MediaBridge**.
- Show the exact text **Powered by Tweest** in the persistent sidebar footer. Keep it readable and visible at default and minimum window sizes. Include it in About information if provided.
- Create an original connected-devices icon, embedded in the window, executable and shortcut.
- Write original code, copy and assets; do not reuse proprietary app code, branding or screenshots.
- Operate locally without accounts, subscriptions, telemetry or cloud services.
- Target Windows 10 and Windows 11 x64. Distinguish intended support from verified compatibility.
- Use model-independent Android discovery. Samsung Galaxy S21 Ultra, S22 Ultra, S23 Ultra and other Galaxy S/A/Z models must not be rejected by model name. Other Android brands use the same authorization flow. Future device compatibility depends on Android interfaces, permissions and testing, not a model whitelist.
- Scope: shared-storage media, local files, native contact vCards and app installation packages. Do not claim iPhone support, private app-data backup, SMS backup, dedicated WhatsApp migration, Secure Folder or cloud-only album access.

## 2. Architecture

Use native Python with Tkinter/ttk. Separate the UI shell, Android transport, filesystem engine, gallery, previews, contacts, app labels, app backups, backup catalog, duplicate detection, desktop integration and diagnostics into modules.

Use Pillow and pillow-heif for image/HEIC previews, imageio-ffmpeg for video, official ADB for Android transport and AAPT2 for APK display labels. Package using PyInstaller windowed one-file mode. Pin working dependencies, provide reproducible build scripts and preserve required third-party notices and source/license information.

Build a small **Twist Contacts Bridge** Android companion in Java or Kotlin. Bundle its signed APK in the desktop executable. Use official Android Contacts APIs and runtime permissions. Request Internet permission only for the optional local companion connection; the ADB contacts provider itself must stay restricted. Restrict its exported provider to the Android debugging shell and reject other callers. Keep signing keys local, excluded from releases and version control.

## 3. UI and branding

Use a polished midnight-indigo/violet theme, lighter blue/slate list rows, generous padding, readable text and simple navigation. Centralize these suggested design tokens:

| Role | Value |
| --- | --- |
| Background | `#100e2b` |
| Surface | `#191638` |
| Raised controls | `#2b2554` |
| Main text | `#f6f4ff` |
| Secondary text | `#beb9db` |
| Accent | `#b6a3ff` |
| Text on accent | `#191034` |
| Border | `#8076b0` |
| List background | `#22344f` |
| Alternating row | `#293f5c` |
| Selected row | `#36587b` |
| Success/tick | `#85efb8` |
| Destructive action | `#ffabbf` |

Use Segoe UI and 8/16/24/32 spacing. Default window approximately 1160 × 790; minimum 900 × 680. Ensure every page is usable at minimum size with scrolling where appropriate. Check contrast in normal, hover, focused, selected and disabled states. Primary button labels remain readable while loading or disabled. Use green or blue ticks, never black X selection marks. Support keyboard focus, Space to select and clear counts/errors/loading/empty states.

Persistent sidebar pages:

1. Media library
2. Overview
3. Phone transfer
4. Create backup
5. Restore backup
6. Contacts
7. Apps
8. Backup manager
9. Activity
10. Connection help

Keep navigation and **Powered by Tweest** visible without clipping.

## 4. Connection and fresh-PC experience

Embed official Windows `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` and notices. Running the packaged app must not require Python, Java, Android Studio or a separate Platform Tools download.

Prefer embedded ADB over legacy SDK settings and PATH. Do not save temporary one-file extraction paths as custom overrides. Provide explicit optional **Custom adb.exe…** and **Use built-in tools** reset actions.

Discover authorized devices dynamically and show actual model/serial. Explain unauthorized/offline states. Guide users through a USB data cable, Developer options, USB debugging, unlocking and approving the computer. Explain that Windows may still need the manufacturer's USB driver, separate from embedded tools. Link to official Samsung driver guidance.

Hide background command windows, bound command timeouts and support cancellation. Do not silently terminate unrelated ADB servers or force-close running apps.

### Wireless connection requirement

Add a **Wi-Fi…** assistant for Android 11+ with a discovery-first workflow: **Find nearby phones → select phone → enter six-digit pairing code → Pair & connect**. Discover `_adb-tls-pairing._tcp` and `_adb-tls-connect._tcp` services using bundled `adb mdns services`. Exclude legacy unencrypted TCP and QR-only advertisements from PIN pairing. Validate all discovered IPs/ports and service names. Match the selected phone's pairing and TLS connection service without guessing ambiguous hosts or connecting an unrelated device. Allow the phone pairing-code popup to be opened after selection; resolve its current pairing port at action time when needed. After pairing resolve its current connection port, accepting either a verified IP serial or that exact service's already-authorized mDNS serial. Verify live authorization and discover the chosen device before announcing success. Already-paired phones use **Connect selected**. Unpaired models may be unknown: display the advertised identifier honestly rather than invent a model. Keep address typing hidden under **Advanced manual connection** for discovery-blocked networks. No automatic access to phones with Wireless debugging disabled is possible. Connect selected must show immediate progress and preserve errors beside its controls. If the phone explicitly rejects authentication, open a masked PIN-entry prompt with on-phone setup instructions; report timeouts/offline states separately from pairing requirements. Repeated selection of the same row must not erase status or typed PINs. Refresh changed connection ports and accept a verified selected-device mDNS alias when the IP serial is absent. Include OPPO/ColorOS setup guidance without claiming unverified menu availability.

Mask and send pairing codes through standard input rather than command arguments, never persist them, and sanitize failures. Run discovery/pair/connect/disconnect in background workers with timeouts, cancellation and progress. Keep the form scrollable and status/Close visible at smaller sizes. Disconnect only the chosen Wi-Fi target and clear its views/previews.

No internet service is required: use the same trusted local network, even when its internet connection is down. Explain guest/client isolation, VPN/firewall blocking and changing phone ports. Do not promise instant speeds. Android 9/10 normally need initial USB for ADB Wi-Fi; do not imply this solves a damaged port on those phones. No Bluetooth transfer is included. Provide steps to revoke pairing on the phone. Physically test pairing and checksum-verified transfers when a supported phone is available; simulated commands do not establish hardware compatibility.


Add independent mDNS discovery using a bundled local discovery library so an empty shared ADB service cache is not the only source. Query only Android TLS pairing/connection advertisements across active IPv4 interfaces, validate results, clean up sockets/browsers, honor cancellation and prefer freshly resolved ports. Preserve working manual connection when multicast is unavailable. Never fill an empty scan with stale entries labelled as currently online or automatically restart a shared ADB server.

Add **Pair with QR code** using Android's documented `WIFI:T:ADB;S:studio-<random>;P:<random>;;` protocol. Generate a fresh random service name and high-entropy password, render a standards-compliant QR image locally in memory and expire the session after five minutes. Instruct the user to use Wireless debugging's dedicated QR scanner. Wait for exactly that session's pairing service, send its password via stdin to ADB, then verify the selected host's authorized connection. Do not treat scanning alone as success, match other sessions or persist QR images/passwords. Cancel/expiry closes and clears the QR view and cancels background work; the user may generate a fresh code to retry. QR pairing still depends on local discovery and does not bypass router/firewall restrictions. Test rendering, exact-session matching, ambiguity rejection, expiry, cancellation, secret redaction and verified success with fixtures, then report physical test results separately.

## 5. Media library and performance

Provide source/device picker, Find phones, Load albums, Local folder, search, Photos/Videos filter, padded album sidebar, selection count and destination controls.

Scan accessible shared storage including DCIM, Pictures, Movies, Music, Documents, Download and Android/media. Skip unsafe names/inaccessible folders while retaining successful results and reporting partial scans.

Display square thumbnails in a responsive grid filling the available area. Use continuous vertical scrolling, never Next/Previous pagination. Support whole-album and individual selection. Distinguish clicking to preview from ticking to transfer. Preserve image aspect ratio and provide video previews; explain muted in-app playback if used and allow external Windows playback.

Virtualize large libraries, use bounded worker threads, prioritize visible items and retain visible widgets. Keep bounded decoded-image and temporary rendered-thumbnail caches. Preserve album and scroll position during scan batches, thumbnail updates and selection changes. Recently loaded thumbnails must not repeatedly reload within the cache budget.

Transfer exactly the selected items to an explicit destination with verification. Preserve different existing destination files and report conflicts. Provide **Delete selected** for phone media with selection-specific confirmation explaining permanent deletion.

## 6. Disconnect privacy

Monitor the live phone connection. On disconnect or authorization loss, promptly clear phone media, app/contact rows, selections and in-app previews. Cancel work, invalidate session tokens, clear temporary media copies and reject late results. Clicking Load albums while offline must not redisplay the previous phone session. Keep local-folder sources distinct. Explain that separately opened Windows players control their own content.

## 7. Contacts

Provide Find phones, Enable contacts and an explicit Load contacts button. Enable contacts installs/updates the companion and opens its permission screen; the user approves Contacts access on the phone. Never bypass consent.

Load live names/numbers into a searchable full-height scrolling table with individual selection, Select all, Clear and counts. Retain exported `.vcf` loading as a fallback.

Export native vCards preserving fields supplied by Android. Stream in bounded batches with progress/timeouts so large phonebooks do not hang at “preparing.” Support:

- **One .vcf file (all selected)**: default editable save name `Contacts_YYYY-MM-DD_HH-MM-SS.vcf`.
- **Individual .vcf files**: dated folder with one complete contact-named file per selected person. Sanitize Windows names and suffix duplicates without overwriting.

Stage and validate exports before publishing; interrupted exports must not appear complete.

Send vCard to phone stages a verified file under Download/TwistMediaBridge and tells the user to finish Import in the phone Contacts app. Do not claim staging completes import.

Delete selected requires live contact ID plus lookup key to protect against reused IDs. Exported vCard rows cannot authorize phone-contact deletion. Confirm permanent/account-sync consequences before action.

## 8. Duplicate-contact finder

Add Duplicates to Contacts. Find candidates sharing normalized full phone numbers or normalized names. Handle Unicode digits and `+`/`00` equivalence; do not guess country codes or match trailing digits alone.

Show scrollable groups and members, all initially Keep. Allow proposed removals while retaining at least one keeper in every overlapping group. Apply proposed selections to the main Contacts table. Actual deletion still requires separate Delete selected and confirmation. No automatic merging/deletion. Clear the review on disconnect. Shared names/numbers are candidates, not proof.

## 9. Apps

Provide a searchable full-height scrolling installed-user-app table. Show real display names, with package IDs secondarily and honest fallback when unresolved. Resolve labels using AAPT2 and APK metadata rather than downloading large app code merely to read a name. Cache by device and installed APK identity/version.

Support individual selection, Select all, Clear, progress and cancellation. Backups use friendly names:

- Single-APK app: `Instagram.apk`.
- Split app: one `Instagram.apks` archive containing all required parts, hashes and a manifest.

Never pretend a base APK is a universal APK or fix split apps by renaming files. Reinstall file accepts `.apk` and the app's `.apks` format, verifies integrity and invokes Android install/install-multiple. Support older numbered-folder backups if migrating prior versions.

Explain that backups exclude private app data, logins and game progress; Android controls signature/version/device compatibility. Delete selected uninstalls only selected packages after confirmation explaining possible data loss.

## 10. File engine

Support explicit sources/destinations using Android shared storage, PC folders and removable drives. Reject same-location/overlapping-folder operations. Provide category filters, progress, cancellation and summaries.

Create backups with versioned manifests, relative paths, sizes and SHA-256 hashes. Mark incomplete operations accurately. Stage writes, verify before publication, reject traversal/symlink/junction escapes and preserve existing different files. Restore preflights all selected backup files before writing anything. Report copied, identical, conflicting and failed items.

## 11. Backup manager

Automatically catalog new successful file/contact/app backups. Allow adding older files, scanning selected folders and refreshing the configured library. Show searchable/filterable name, type, date, item count, size and verification state; retain missing-drive entries.

Provide Open folder, Verify, Restore selected and Remove from list. Removing a catalog row never deletes saved files. Preserve the original hash baseline: refresh/re-add must not silently accept tampering. Imported backups establish their baseline at import, an integrity reference rather than proof of authenticity.

Route restores correctly: files to destination, APKs to phone, vCards staged for import. Validate manifests and archive paths before extraction.

## 12. Single executable and shortcut

Deliver a clean versioned folder containing one user-facing `TwistMediaBridge.exe`, with dependencies, icons, companion, Android tools and notices embedded. Explain normal runtime extraction and separate settings/backups.

Maintain an application copy under `%LOCALAPPDATA%/TwistMediaBridge/Application/` and settings/catalog/logs under `%LOCALAPPDATA%/TwistMediaBridge/`. Create a **Twist MediaBridge** shortcut in the actual Windows desktop folder, including redirected desktops. Check every launch: recreate missing shortcuts and repair stale targets/icons even if an installation marker exists. Target the installed copy so moving the original download does not break it.

Preserve user settings and backups across updates. Handle an older running instance gracefully without forced termination. Ordinary launch/shortcut creation should not require administrator rights; driver installation is separate.

## 13. Verification

Use disposable fixtures for all destructive tests. Cover:

- SDK-free embedded tool selection, legacy paths, explicit override and reset.
- Several Galaxy generations and other brands accepted by discovery without model filters.
- Verified backup/restore, corrupt manifests, unsafe paths, overlaps and destination conflicts.
- Large virtualized galleries, stable scan/scroll state and thumbnail reuse.
- Disconnect clearing, offline Load albums and late-result rejection.
- Native contact export batching, combined/individual vCards, editable timestamp defaults, duplicate names and cancellation.
- Real app labels, single/split packaging, corrupt archives and restore verification.
- Exact delete targets, canceled confirmations and stable contact identity guards.
- Duplicate matching, overlapping groups and keep-one protections.
- Catalog baselines, missing locations and non-destructive removal.
- Shortcut recreation after deletion despite an existing marker.
- All UI pages at default/minimum sizes, contrast and visible **Powered by Tweest**.

Run the actual packaged app's isolated self-test: embedded ADB with SDK locations removed from PATH, image/HEIC/video previews, checksum backup/restore round trip and shortcut creation in a temporary desktop folder. Test Windows 10/11 and physical phone models when available. Clearly report deferred hardware/environment checks; simulations do not establish physical compatibility.

## 14. Deliverables

Provide complete source, dependencies, desktop/companion build scripts, original icon, tests, user README, third-party notices and the clean single-executable release. State the exact output path and unresolved limitations. Exclude signing secrets, personal device data, caches and backups. Never silently omit requirements or claim unperformed tests.


For six-digit pairing, never imply that the PC sends a phone notification or creates the phone PIN. Guide users to the phone's Pair device with pairing code control. Wait for the selected host's non-QR pairing-service advertisement before opening a PC code-entry dialog, and reject ambiguous services. Show a clear cancellable wait/timeout and keep setup help available. Tests must distinguish a successful PIN pair command from reconnecting an already-authorized device. A previously connected or QR-paired device is not evidence of a completed PIN test.


## Added local companion connection

Preserve USB and existing Android wireless debugging. Also implement the permission-based encrypted Android 6+ local Wi-Fi companion described in COMPANION-WIFI.md, including Android 9 support, native QR scanning, certificate pinning, one-use expiring enrollment, approved folders, chunked verified transfers, phone thumbnail caching, contact exports/deletion, APK backups and disconnect privacy. App installation/uninstallation remains on existing debugging connections. No Bluetooth transport is currently implemented. Never claim physical compatibility from simulated tests.

