# Installing Milcrid on Windows (beta)

**Milcrid** is an app in which an AI that runs on your own PC works alongside you. This is an early beta version,
free for private, non-commercial use. **Use at your own risk** – please read the notice the installer shows.

## What you need
- Windows 10 or 11 (64-bit)
- For usable speed: a graphics card with 8 GB of memory or more (NVIDIA recommended). Without one, the AI answers
  very slowly (a minute per answer instead of seconds).
- About 20 GB of free disk space and an internet connection for the setup.

## Steps
1. Download `Milcrid-Setup-<version>.exe` (about 620 MB). **Your browser holds the file back** because this small
   project is new: Edge says *“Milcrid-Setup-….exe isn't commonly downloaded”*. To keep it: open the download list
   (the arrow at the top right, or type `edge://downloads`), move the mouse onto the entry, click the three dots
   **…** and choose **Keep**. Edge then asks once more whether you trust the file: click the small arrow next to
   **Delete** and choose **Keep anyway**. (In a German Edge: *Beibehalten*, then *Trotzdem beibehalten*.) Until you
   do, there is no file in your Downloads folder – and if you close the browser first, the download is gone.
2. Double-click the file. Windows may show **“Windows protected your PC”**, because this project has no paid signing
   certificate. Click **More info**, then **Run anyway**. (If you already clicked *Keep* in Edge, this step is
   usually skipped.)

   **If Windows says “Smart App Control blocked an app that may be unsafe”** (only *Okay* and *Get apps from the
   Store*, no *Run anyway*): Smart App Control is switched on, and it stops every program that is not signed – there is
   no exception for a single program. Milcrid can then only be installed if you switch it off: **Windows Security ›
   App & browser control › Smart App Control › Off**. This is a setting for your whole PC, so decide for yourself
   whether you want that; you can switch it back on in the same place afterwards.
3. **Wait.** For up to a minute nothing seems to happen – Windows is scanning the file. Don't click again; the
   installer appears by itself.
4. Read the notice, tick the box, click **Next**, then **Install**. No administrator rights are needed; Milcrid is
   installed for your user account only. This takes one to two minutes.
5. Click **Finish**. Milcrid starts and opens **“Setting up the AI”**:
   - **Ollama** (the free program that runs the AI model, about 1.6 GB): *Download and install*. If Ollama opens its
     own window afterwards, just close it.
   - **AI model**: *Standard* (qwen3.5:9b, 6.6 GB) or *Small* (qwen3.5:4b, 3.4 GB).
   - Or **Start without AI** – Milcrid's apps work, only the chat cannot answer. The setup window comes again at
     the next start.
6. After that the AI works without the internet. Open the **Milcrid Handbook** (button on the right) – or just say
   “open handbook”.

## Updating to a newer version
**From version 0.3.5 on** – one click, no browser:
1. In Milcrid: **Portal › Update › Milcrid Update**, then **Look on GitHub for a new version**. Milcrid only looks
   when you click. If a newer version is there, Milcrid shows what is new and what was fixed.
2. Click **Install now**. If something in Milcrid is not saved yet (the text of the online AI, a drawing in Milcrid
   Sketch, an appointment you are writing), Milcrid asks first. Other programs stay open – nothing is lost there.
3. Milcrid downloads the new version, checks it against the checksum GitHub gives, closes itself and installs it.
   A small window says "Milcrid is being updated"; after about a minute Milcrid starts again by itself. Your data
   stays (appointments, notes, settings, the AI model).

**Version 0.3.4 and older** – once more the way through the download page:
1. In Milcrid: **Portal › Update › Milcrid Update**, then **Look on GitHub for a new version**. If a newer version is
   there, **Open the download page** takes you to it.
2. Download the new `Milcrid-Setup-<version>.exe` – the browser holds it back as described in step 1 above. After
   "Keep", open the download list and click **Open file** – the browser does not start it by itself.
3. **Close Milcrid** (the X at the top right of its window), then run the installer. If Milcrid is still open, the
   installer says so and changes nothing – close Milcrid and start the installer again.
4. The installer suggests the folder of your installation; leave it as it is. It replaces the program and keeps
   your data (appointments, notes, settings, the AI model).

## Two things Windows may ask later
- **Windows Security: “Do you want to allow public and private networks to access this app? – Python”.** This can
  appear the first time Milcrid searches the internet (Milcrid's AI part is written in Python). Click **Cancel** –
  Milcrid does not need to be reachable from the network, and searching works either way.
- **Ollama update.** Ollama offers its own updates from time to time. When Ollama restarts, Milcrid keeps working –
  the next answer just takes a few seconds longer.

## Removing it
Windows Settings › Apps › Installed apps › *Milcrid (beta)* › Uninstall. You are asked whether your Milcrid
folder (`Milcrid` in your user folder: settings, notes, memory) should be deleted too. Ollama and the AI models have
their own uninstaller (*Ollama* in the same list).

## If something goes wrong
- Log files are in your `Milcrid` folder: `backend.log`, `ki-einrichtung.log`.
- “The AI is not connected”: start *Ollama* from the Start menu, then start Milcrid again.

License: PolyForm Noncommercial 1.0.0 (`LICENSE.md`). Included components: `THIRD-PARTY-NOTICES.txt`.
