# Twist Companion Wi-Fi

Added alongside USB and Android wireless debugging in MediaBridge 1.14. This is a new local Wi-Fi protocol, not a Quick Share integration or Bluetooth transport. It is designed for Android 6+ including the Android 9 Galaxy Note8; physical Note8 testing is still required.

## Connect without a cable

1. Open `Ready-to-use-1.14.10/TwistMediaBridge.exe` and click **Companion Wi-Fi** in the sidebar.
2. Click **Save phone app…**. Send the exported `TwistCompanion.apk` to your phone through Quick Share, Bluetooth file sharing, an SD card or another trusted method. Install it and open **Twist Companion**. No Play Store or USB debugging is needed for this connection. Android may ask you to allow installation from the app used to open the APK.
3. On the phone, click **Choose media folder** and approve a local folder such as DCIM or Pictures using Android’s folder picker. Repeat for other folders. Use **Choose receive folder** to choose where PC transfers go; the first folder is used if none was chosen separately. Android may prevent choosing storage roots on newer versions, so choose individual folders.
4. Optionally tap **Allow contacts access** and approve Contacts permission.
5. Keep both devices on the same trusted local network. On the PC, select its Wi-Fi/LAN address and click **Start pairing**.
6. On the phone tap **Scan PC QR**, allow Camera permission, scan the PC QR, then approve **Connect**. This scanner is inside Twist Companion; do not use Android’s Wireless debugging scanner.
7. Leave the phone companion open. In MediaBridge select the phone ending in **Companion Wi-Fi**, then **Load albums**, **Load contacts**, or **Load apps**.

The PC may use Ethernet to the same router. Internet is not needed. Network isolation, a VPN or Windows Firewall can block local access. If Windows asks, allow MediaBridge on the private network you trust; the app does not change firewall rules. Select another PC address if there are VPN/virtual adapters.

If scanning is unavailable, **Copy pairing link** on the PC and paste the full link into the phone companion. Treat it as a private temporary credential. It expires after five minutes and is consumed by one phone.

## Available through the companion

| Feature | Behavior |
| --- | --- |
| Albums, thumbnails and previews | Only phone folders explicitly approved through Android’s folder picker |
| File/media backups and transfer to PC | Chunked transfers, SHA-256 verification, existing backup manager |
| Transfer / restore files to phone | Files go beneath the chosen receive folder; conflicts are preserved |
| Contacts backup | Live names/numbers; combined or individual native vCards after permission approval |
| Send vCard to phone | Copies the file; import using the phone’s Contacts app |
| Duplicate contacts and selected deletion | Existing review/confirmation flow and Contacts permission |
| Media deletion | Existing PC confirmation, limited to approved indexed photo/video files |
| App listing and APK/APKS backup | Uses Android app names; excludes private data and logins |
| App installation | Companion 1.5: send an APK or Twist .apks backup, then approve Android's installer on the phone; USB and wireless debugging also remain available |
| App uninstallation | Continue using USB or Android wireless debugging |

Some installed applications can restrict access to their installation files. Android permissions, OEM policies and document-provider behavior still apply. Private app folders, Secure Folder and cloud-only albums are not exposed.

## Privacy and session controls

- Each pairing creates a fresh TLS certificate and a random 256-bit enrollment token. The QR pins that exact certificate in the phone; traffic is encrypted with TLS 1.2 or newer.
- Pairing requires approval in the phone app, expires after five minutes and accepts only one phone. Session credentials are held in memory rather than settings files.
- Phone permissions remain under Android’s control. Folder grants persist for convenience and can be removed with **Forget approved folders**.
- The companion requests Android’s network permission to reach your PC. Its connection code has no cloud endpoint. The existing ADB-only contacts provider remains restricted to the debugging shell and the companion’s own process.
- Use **Disconnect** on the PC or phone to end access. On connection loss, the desktop clears displayed media/contacts, selections and preview cache after detecting the loss (heartbeat timeout up to 15 seconds). Reconnection needs a fresh pairing session.
- Companion 1.3 runs a user-visible foreground connection service with an active notification and Disconnect action. CPU/Wi-Fi locks are held only for the active session and released at shutdown. Brief transport errors are retried; genuine loss still hides desktop data after up to 15 seconds. OEM power policies can still terminate the app; physical background testing remains required. Unfinished phone upload cache is cleaned on disconnect or next app startup.

## Validation

The Android APK is compiled, signed with the existing companion key, and signature-verified. Desktop protocol tests use a real local HTTPS server and a simulated phone: authentication, expired/reused credentials, cancellation, late responses, thumbnails, large/chunked downloads/uploads, backup checksums, native vCards and named APK exports. Real Tk tests cover pairing UI, contacts, gallery disconnect privacy and opening the existing ADB wireless dialog with the companion present.

These checks do not establish physical Note8, camera-scanning or Android document-provider compatibility. Test those on your phone before treating the new connection as finalized. Bluetooth transport is not implemented in this release.

### Album filename compatibility fix (1.14.1)

Android-only folder and file names are assigned stable Windows-safe aliases for display and backups. Original phone names are retained for reads, thumbnails and explicitly confirmed deletion; no phone files are renamed. This desktop-only update does not require reinstalling the phone companion.




### Connection stability update (desktop 1.14.2 / companion 1.3)

Update the existing phone APK without uninstalling it. The phone connection is owned by a foreground service instead of the Activity lifetime, with a visible Disconnect notification. Short transport failures get bounded retries; certificate failures and revoked/expired sessions remain final. PC poll requests are redelivered using the same request ID after a lost response, and the phone caches completed results to avoid repeating mutations. Cancelled results do not terminate the session. The 15-second privacy timeout is unchanged; an expired token cannot resume a hidden library.

Android 15+ imposes foreground data-sync time limits. This service also ends after six hours and never restarts itself on boot. Device-specific battery restrictions can still apply. New tests exercise retry bounds, certificate/session failure rejection, cancellation, lost-poll redelivery, duplicate-result handling and idle heartbeats; these do not prove a physical Samsung endurance test.



### Companion media deletion routing fix (desktop 1.14.3)

Corrects the desktop media-delete dispatcher to use the phone companion’s approved-folder delete operation. The original phone path is retained for Windows-safe aliases, the entire selection is validated before any deletion request, only selected items are sent, and per-file failures remain selected. USB deletion and companion app-install/uninstall restrictions remain unchanged. Error dialogs show a bounded summary. This desktop update works with Companion 1.3 already installed; no phone APK reinstall is needed.



### Batch export reliability (desktop 1.14.10 / companion 1.4)

Companion heartbeat failures are now judged against successful authenticated traffic from all request types. An overloaded heartbeat request does not terminate a session while transfers or other control requests are succeeding. Failed poll/result exchanges can recover while that recent authenticated traffic proves the session is alive; certificate or session rejection remains terminal. The desktop privacy timeout is unchanged at 15 seconds without authenticated traffic. Incoming staging files are removed after each completed or failed export item, only inside the transfer's own temporary directory. Original source files remain untouched. Update the phone APK in place to version 1.4, then pair again using the updated PC app. The 123-test suite includes multi-item, multi-chunk and conflict-preservation exports; Android health policy is also tested with simulated heartbeat failures during bulk traffic. Physical Note8 batch testing is still required.


### App installation over Companion Wi-Fi (desktop 1.15 / Companion 1.5)

Update the phone with `Phone-app-1.5/TwistCompanion.apk` (choose Update; do not uninstall). Open Companion and pair again. On the PC, open Apps → Reinstall file, select an APK or a Twist .apks backup, then follow the approval screen on the phone. Older folder backups also work through Old folder. No receive-folder permission is needed for installation.

On Android 8 and newer, enable “Allow from this source” for Twist Companion when prompted, return to the installation screen and tap Continue again. Android must still approve the app. The PC waits up to five minutes and reports Android's confirmed result. Cancellation, expiry or disconnect abandons the pending installer session and removes its staged files; a completed installation cannot be rolled back by cancellation.

APK signatures, minimum Android version, hardware architecture, split compatibility and phone security policies still apply. An app requiring a newer Android version cannot be made compatible with Note8/Android 9 by changing the transfer method. Private app data and logins are not restored. This is a standard Android PackageInstaller flow, not a Samsung-only path. Existing USB and Android wireless-debugging install handlers are preserved. Phone hardware validation is still needed for this new flow, including Android 9 and newer devices.
