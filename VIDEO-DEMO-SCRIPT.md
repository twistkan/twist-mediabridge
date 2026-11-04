# Twist MediaBridge — video demonstration script

**Video title:** Twist MediaBridge: Your Android Media, Contacts and Apps on PC  
**Format:** Windows screen recording with voice-over, captions and short phone-camera inserts  
**Target length:** Approximately 8 minutes; timings are editing guides, not promises about operation speed  
**Build shown:** Twist MediaBridge 1.13  
**Brand credit:** Powered by Tweest

This is a production script, not an automated video-generation program. Record actual app behavior, then edit the footage to match the narration. Quoted paragraphs are the voice-over; action lists and captions are production directions, not spoken lines.

## Recording preparation

- Record the desktop at 1920 × 1080 if available. Keep the app large enough for its controls to be readable.
- Use a test Android phone with a small demo album, fictional contacts and a disposable app. Avoid personal photos, real phone numbers, serial numbers, account details and sensitive paths. Blur any that appear incidentally.
- Create a folder such as `Documents\Twist Demo` for transfers and backups. Use a clean destination folder for the restore demonstration.
- Include two fictional contacts with the same test number to demonstrate duplicate review. Use a dedicated test profile or device for anything that might delete or uninstall.
- Capture the USB-debugging approval and Contacts permission prompts on the phone. If already authorized, record the relevant settings instead; do not pretend a prompt appeared.
- Silence notifications and hide unrelated desktop windows. Use a subtle cursor highlight, readable captions and gentle zooms on important controls.
- Use the original app icon and midnight/violet palette. Put **Powered by Tweest** on the opening and closing video cards. The current 1.13 app does not yet contain that UI label; do not add a fake label to screen footage. A future branded build can show its real sidebar credit.
- Capture operations through completion before editing. Speed up or cut long waits with a visible “Loading sped up” or “Time shortened” caption. Do not imply all devices load or transfer instantly.

## Scene 1 — introduction · 00:00–00:25

**Screen actions**

Show an original title card, followed by a brief montage of the gallery, Contacts, Apps and Backup manager. Settle on the desktop shortcut.

**Voice-over**

> Meet Twist MediaBridge: a Windows desktop app for bringing your Android media, contacts and app installation backups together in one place. In this walkthrough, we'll connect a phone, transfer selected photos, save contacts, back up an app and manage our backups. Everything shown uses local files and a USB connection, with no account required.

**On-screen text:** `Twist MediaBridge` · `Powered by Tweest` · `Your data. Your devices.`

## Scene 2 — launch and connect · 00:25–01:15

**Screen actions**

1. Open `Ready-to-use-1.13\TwistMediaBridge.exe`, or the current delivery executable supplied to the viewer.
2. Briefly show the desktop shortcut. If demonstrating automatic creation, use a prepared recording of a real missing-shortcut launch.
3. Open **Connection help** and highlight the built-in tools guidance.
4. Insert phone footage: enable USB debugging in Developer options, connect a data cable, unlock and approve the computer.
5. Click **Refresh phones**, or return to Media library and click **Find phones**. Select the connected phone.

**Voice-over**

> Start by opening the single Twist MediaBridge executable. It creates a desktop shortcut for future use, and recreates it on a later launch if it's missing. The Android connection tools are already included, so you don't need a separate Platform Tools or Android Studio installation.
>
> On your phone, enable USB debugging in Developer options. Connect a USB data cable, unlock the screen and approve this computer. Then refresh the phone list and select your device. Samsung Galaxy and other Android phones use the same connection flow. If Windows doesn't detect your phone, check the cable, authorization and manufacturer USB driver guidance here.

**Captions:** `Built-in Android tools` · `Enable USB debugging` · `Approve this computer`

**Production note:** Developer options menus differ by phone. Do not present one Samsung menu path as universal or claim every model is tested.

## Scene 3 — albums, thumbnails and previews · 01:15–02:00

**Screen actions**

1. Open **Media library**, select the phone and click **Load albums**.
2. Show albums appearing; choose the prepared demo album.
3. Scroll down and back up through the thumbnail grid.
4. Click a photo to preview it, close the preview, then preview a short demo video.
5. Briefly demonstrate search or Photos/Videos filtering.

**Voice-over**

> In Media library, choose your phone and click Load albums. Pick an album on the left, then browse its photos and videos in the scrolling grid. You can scroll through the collection without clicking through pages. Click a thumbnail to inspect the media, and use search or the media filter to narrow the view.
>
> This browser reads accessible files stored on the phone. Cloud-only items, Samsung Secure Folder and some Gallery-only groups aren't available through this connection.

**Captions:** `Browse albums` · `Click to preview` · `Scroll continuously`

## Scene 4 — transfer selected media · 02:00–02:35

**Screen actions**

1. Tick two photos and one video; pause on the selection count.
2. Briefly point out **Select this album** without changing the intended selection.
3. Click **Save to…** and select the prepared demo destination.
4. Click **Transfer →** and show the actual completion result.
5. Open the destination folder and show the transferred files.

**Voice-over**

> Tick the photos and videos you want to copy, or select the whole album. Choose a destination folder on your PC and start the transfer. Once it completes, open the folder to check your files. If a different file already exists at the destination, Twist MediaBridge preserves it and reports the conflict instead of silently replacing it.

**Captions:** `Select → Choose destination → Transfer` · `Existing different files are preserved`

## Scene 5 — load contacts and choose a backup format · 02:35–03:45

**Screen actions**

1. Open **Contacts**, select the phone and click **Enable contacts**.
2. Show the real companion installation/opening flow on the phone. Tap **Allow contacts access** and approve permission.
3. On the PC, click **Load contacts** and show fictional names in the table.
4. Select a few contacts and choose **One .vcf file (all selected)**.
5. Click **Back up selected**, pause on the timestamped default filename, then save and show completion.
6. Switch to **Individual .vcf files**, choose a folder and complete a second backup.
7. In Explorer, show the contact-named `.vcf` files. Optionally open a fictional contact in a compatible viewer.

**Voice-over**

> For live contacts, first click Enable contacts. On the phone, open Twist Contacts Bridge and approve Contacts access. Return to the PC and click Load contacts. You can search, tick individual people or select everyone.
>
> There are two backup formats. The combined option saves all selected contacts in one vCard file. The save dialog suggests Contacts followed by the date and time, and you can replace that name.
>
> For individual files, switch the format and choose a destination folder. Each selected person gets a separate, contact-named vCard. This makes it easier to inspect or share a single saved contact using a compatible contacts application on your PC. Wait for the completion message before using the backup.

**Captions:** `Approve Contacts permission on the phone` · `One phonebook file or individual vCards` · `Editable date-and-time filename`

## Scene 6 — review duplicate contacts · 03:45–04:25

**Screen actions**

1. Click **Duplicates** using the fictional duplicate contacts.
2. Show a candidate group and its members, initially marked Keep.
3. Mark one proposed removal while leaving a keeper.
4. Apply the marked selection back to Contacts.
5. Point out **Delete selected**, then clear the selection. Do not delete during this scene.

**Voice-over**

> The duplicate finder helps you review contacts with matching names or full phone numbers. These are suggestions, so check each group before deciding. Every contact starts as Keep. Mark the entries you might remove while retaining the contact you want.
>
> Applying the selection doesn't delete anything. It returns those proposed removals to the main list, where deletion still needs a separate action and confirmation. For this demo, we'll clear the selection and keep both contacts.

**Captions:** `Review candidates` · `Keep at least one` · `No automatic deletion`

## Scene 7 — back up and reinstall app packages · 04:25–05:20

**Screen actions**

1. Open **Apps** and click **Load apps**.
2. Search for a disposable demo app and select it.
3. Click **Back up selected** and show the completed output in Explorer.
4. Show a real `.apk` output and, if available, a real `.apks` split-app backup. Do not fabricate either output type.
5. Click **Reinstall file** and show the picker. Cancel unless recording a separately verified reinstall on the test phone.

**Voice-over**

> In Apps, load the installed app list and search by name. Select an app and back up its installation files. A single-package app saves as a friendly-named APK. An app that needs multiple split packages saves as one APKS archive containing its required parts.
>
> To reinstall a saved package, choose Reinstall file and select the backup. Keep split archives intact; renaming one to APK won't make it a standalone installer. Android still checks device compatibility, versions and signatures. These backups contain installation packages, not private app data, saved logins or game progress.

**Captions:** `.apk = single package` · `.apks = split-package archive` · `Private app data is excluded`

**Production note:** If the picker is canceled, label the footage `Restore entry point`; do not narrate that a reinstall succeeded. Use **Old folder…** only if demonstrating a genuine legacy backup.

## Scene 8 — file backup, restore and Backup manager · 05:20–06:30

**Screen actions**

1. Open **Create backup**. Choose a small prepared local demo folder or phone source and supported categories.
2. Start the backup and record its completion.
3. Open **Backup manager** and show the newly cataloged backup alongside contact/app demo backups.
4. Search or filter the catalog; select the file backup and click **Verify**.
5. Choose the prepared empty PC destination and use **Restore selected**. Record the confirmation, completion and resulting files.
6. Point out **Add backup file**, **Scan backup folder**, **Open folder** and **Remove from list**.

**Voice-over**

> Create backup saves supported files with a manifest and checksums. Let's make a small example, then open Backup manager. Successful new backups appear here automatically, and older backups can be added by file or folder.
>
> Select a backup and choose Verify to check its recorded integrity. For this file backup, choose an empty PC destination and restore it. Once the operation finishes, check the restored files in Explorer.
>
> Backup manager also handles app and contact backups through their appropriate restore workflows. Open folder takes you to the saved location. Remove from list only removes the catalog entry; it doesn't delete your backup files.

**Captions:** `Create → Catalog → Verify → Restore` · `Remove from list keeps saved files`

**Production note:** Show actual checksum verification, not a claim of encryption. Use a file backup for the completed restore shot so the scene does not falsely imply automatic contact import.

## Scene 9 — sending contacts back and deletion controls · 06:30–07:05

**Screen actions**

1. In Contacts, use **Send vCard to phone** with the fictional demo backup.
2. Show the staged file and briefly show the phone Contacts app's Import entry point.
3. Show **Delete** in Media or **Delete selected** in Contacts/Apps using only disposable selections. If opening a confirmation, choose Cancel.

**Voice-over**

> To send saved contacts back, choose Send vCard to phone. The app places the file in Download, inside TwistMediaBridge. Finish the import in your phone's Contacts app; copying the file alone doesn't add the contacts.
>
> Media, Contacts and Apps also let you delete selected items. Read the confirmation carefully: media deletion is permanent, uninstalling an app can remove its data, and contact deletion may sync to your linked account. Here, we'll cancel and leave the test content untouched.

**Captions:** `Finish contact import on the phone` · `Deletion requires confirmation`

## Scene 10 — disconnect privacy and closing · 07:05–07:45

**Screen actions**

1. Reopen the connected phone's Media library and display the test album.
2. Unplug the phone and record the actual clearing behavior.
3. Try **Load albums** while disconnected and show the current offline behavior without exposing old thumbnails.
4. End with an original closing card and the desktop shortcut.

**Voice-over**

> When the phone disconnects, Twist MediaBridge clears the phone's in-app content and previews after detecting the disconnection. Loading albums while offline shouldn't bring back the previous session. Files you've deliberately backed up remain at their saved locations, and separately opened Windows players control their own content.
>
> That's the everyday workflow: connect, browse, select and back up. Keep your saved backups somewhere protected, and check a restore on your intended device before depending on it. Twist MediaBridge. Powered by Tweest.

**Closing card:** `Twist MediaBridge` · `Connect. Browse. Back up.` · `Powered by Tweest`

**Small closing note:** `Recorded on Windows 10. Windows 11 and individual phone models require separate testing.`

## Editing and delivery notes

- Keep narration clear and conversational. Let important dialog names and completion messages remain visible long enough to read.
- Use restrained cuts and zooms rather than transitions that obscure steps. Keep background music low beneath speech and use properly licensed audio.
- Add captions matching the final spoken audio. Update chapter timestamps after editing; the scene timings above are approximate.
- If an operation fails during recording, fix or explain it before showing a successful result. Do not replace real failures with fabricated success screens.
- Never describe backup files as automatically encrypted, every phone as verified compatible, or a staged vCard as an imported phonebook.
- Suggested output: a 1080p MP4, a caption file and an original thumbnail reading **“Twist MediaBridge — Complete Walkthrough”**.
- Final review: readable controls, accurate button labels, no private data, genuine completion results, clear APK/APKS distinction and visible **Powered by Tweest** opening/closing credit.

## Optional 30-second teaser

**Visuals:** Brief title card → scroll album → tick and transfer → contact-named vCards → friendly-named app backup → Backup manager → closing card.

**Voice-over**

> Your Android content, organized on your PC. With Twist MediaBridge, browse albums, preview media and transfer selected files. Save contacts as one phonebook or individual vCards. Back up app installation packages and keep your saved backups organized in Backup manager. Connect by USB, approve access and get started. Twist MediaBridge. Powered by Tweest.

**Overlay:** `App backups exclude private data. Device permissions and compatibility apply.`

## Optional replacement connection scene — Wi-Fi without internet

Use this in place of Scene 2 when recording with an Android 11+ phone. Record real successful pairing and transfer before describing them as working; this scene remains a recording plan until verified on supported hardware.

**Actions:** Join the phone and PC to the same trusted local network. On the phone enable Wireless debugging. In MediaBridge click Wi-Fi… → Find nearby phones and select the phone. On the phone open Pair device with pairing code, enter only its six-digit code in MediaBridge and click Pair & connect. Do not type addresses or ports. Record the actual automatic connection, load albums and transfer a test photo. Show completion and the saved result. For an already-paired phone demonstrate Find nearby phones → Connect selected. If demonstrating loss of internet, disconnect the router's internet uplink while keeping its local network running; do not disable Wi-Fi itself.

**Voice-over:**

> No cable? On Android eleven or newer, enable Wireless debugging and click Find nearby phones in MediaBridge. Select your phone, open its pairing-code screen and enter the six-digit code here. Choose Pair and connect, and MediaBridge handles the connection details. Already paired? Choose Connect selected. Once connected, load your albums and copy selected media as usual. This uses your local network and can work when the internet is down. Discovery still needs the phone to advertise Wireless debugging and the router to allow local connections. Android nine and ten normally need USB first.

**Captions:** `Find → Select → Enter code → Pair & connect` · `Android 11+` · `No IP typing in the normal flow` · `Internet not required`

## Optional QR-pairing insert

**Actions:** Click Pair with QR code. On a supported phone open Wireless debugging → Pair device with QR code and scan the desktop code. Keep the PC window visible through pairing and verified connection. Show Load albums and a completed sample transfer only if both actually succeed. Never publish a live QR password in screenshots or reusable demo assets; record an expired/disposable test session.

**Voice-over:**

> Prefer scanning? Choose Pair with QR code and use the QR scanner inside your phone's Wireless debugging settings. No PIN or address typing is needed. Keep both devices on the same local network and wait for MediaBridge to confirm the connection. The code expires after five minutes. QR pairing still needs local discovery, so it won't bypass an isolated guest network or blocked phone connection.

**Captions:** `Use the Wireless debugging QR scanner` · `Wait for verified connection` · `Same local network; internet not required`

## Code-pairing clarification

In the code-pairing scene, explicitly show the phone's **Pair device with pairing code** button being tapped. The code is generated there; the PC does not send a notification. Show MediaBridge waiting for that phone screen before asking for its code. Do not use an already-connected device as proof that the code method completed. Blur or omit a live PIN from published footage.
