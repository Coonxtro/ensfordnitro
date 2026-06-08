# Discord <> Roblox Link Bot

This project is a Discord bot designed to link Discord accounts with Roblox users. It provides robust functionality for user verification, role mapping based on potential in-game achievements (as suggested by the database schema), and includes a web API for external integrations.

## Features

- **Link Accounts**: Users can securely link their Discord account to their Roblox username.
- **Unlink Accounts**: Functionality to remove existing links.
- **Role Mappings**: Manage mappings between specific achievements/triggers and Discord roles (found in `cogs/addmapping.py`).
- **Web API**: Built-in Flask server (via `waitress` for production) to handle external requests, such as assigning roles dynamically (`api/assign_role.py`).
- **SQLite Database**: Lightweight and efficient local storage for user links and configuration.
- **Caching**: Implements caching for Roblox API lookups to respect rate limits (`R.py`).

## File Structure

- `bot.py`: The main entry point for the Discord bot and the background Flask server.
- `database.py`: Handles SQLite database connections and schema initialization.
- `flask_app.py`: Configures the Flask application and blueprints.
- `R.py`: Contains utility functions (like `fetch_roblox_id`) and caching mechanisms.
- `cogs/`: Contains Discord command modules (Cogs):
  - `link.py`: `/link` command logic.
  - `unlink.py`: Logic to unlink accounts.
  - `addmapping.py`: Commands to manage role mappings.
- `api/`: Contains API route definitions.

## Setup & Installation

### Prerequisites
- Python 3.8+
- A Discord Bot Token (from the [Discord Developer Portal](https://discord.com/developers/applications))

### 1. Install Dependencies
Install the required Python packages using pip:

```bash
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file in the root directory and add the following variables:

```ini
# Required
BOT_TOKEN=your_discord_bot_token_here

# Optional
PORT=3000
DB_PATH=bot.db
CACHE_TTL=3600
DEBUG=False
```

### 3. Running the Bot
You can start the bot using Python directly or provided batch scripts.

**Via Python:**
```bash
python bot.py
```

**Via/Windows Batch Script:**
- `start.bat`: Likely configured to run the bot.
- `run.bat`: Alternative runner.

## Usage

### Discord Commands
- `/link [roblox_username]`: Links your Discord account to the specified Roblox user.
- `/unlink`: Unlinks your current Roblox account.
- `!addmapping` (or similar): Configure role rewards (check specific cog for syntax).

### API
The bot runs a web server (default port 3000). Endpoints such as `assign_role` are available for external services to trigger role updates on Discord users.

## Database
The project uses SQLite. The database file (`bot.db` by default) is automatically created on the first run with tables:
- `verify`: Stores Discord ID <-> Roblox ID links.
- `role_mappings`: Stores configuration for awarding roles based on achievements.
