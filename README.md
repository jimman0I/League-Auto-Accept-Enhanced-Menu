Here's a ready-to-use GitHub repository description. You can paste the short version into the repo's **"About"** section, and use the full markdown for your `README.md`.

---

### 🔹 Short Tagline (for GitHub "About" section)
`Automate League of Legends queue acceptance, champion select, runes, spells, chat, and anti-AFK using the official LCU API.`

---

### 📘 Full README Description

# ⚔️ League Auto-Accept

A lightweight, Python-based desktop tool that interfaces with the **League of Legends Client API (LCU)** to automate repetitive pre-game and in-game tasks. Built for convenience, reliability, and a clean aesthetic, it handles matchmaking acceptance, champion selection, loadout configuration, lobby chat, and AFK prevention—all without modifying game memory or injecting code.

## ✨ Features
- 🟢 **Auto Accept** – Instantly accepts ready checks & matchmaking queues
- 🎯 **Auto Pick/Ban** – Selects and **locks in** your preferred champion automatically
- 📖 **Auto Runes & Spells** – Applies preset summoner spells and rune pages after lock-in
- 💬 **Auto Chat** – Sends custom messages in the champion select lobby
- 🛡️ **Anti-AFK** – Prevents in-game disconnects by simulating activity when idle
- 💾 **Persistent Config** – Saves your preferences to `lol_config.json` between sessions
- 🖥️ **Hextech-Themed GUI** – Clean, responsive Tkinter interface with real-time phase tracking & live logs
- 🔌 **Zero Dependencies** – Uses Python's standard library + `requests`

## ⚙️ How It Works
The application connects to the running League Client via its local REST API, authenticates using the `lockfile`, and continuously monitors the game flow phase (`ReadyCheck`, `ChampSelect`, `InProgress`). Actions are triggered automatically at the correct moments, ensuring smooth execution without manual input.

## 🚀 Quick Start
1. Ensure Python 3.8+ is installed
2. Install dependencies: `pip install requests`
3. Run the client normally
4. Execute: `python lol_auto_accept_gui.py`
5. Configure picks, bans, spells, runes, and toggles via the GUI
6. The app will auto-connect and run in the background

## ⚠️ Disclaimer
This tool interacts **only** with the official League Client API (LCU) through documented local endpoints. It does **not** read/write game memory, inject DLLs, or modify client files. Use at your own discretion. Riot Games does not officially endorse or support third-party automation tools.

## 🛠️ Tech Stack
`Python 3` • `Tkinter` • `Requests` • `ctypes` • `LCU REST API`

---

💡 *Tip for your repo:* Add a `requirements.txt` with just `requests` and a `LICENSE` file (MIT is common for tools like this). Let me know if you want a badge setup, installation script, or automated release workflow!