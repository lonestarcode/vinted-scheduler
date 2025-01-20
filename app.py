from flask import Flask, render_template, jsonify, request
from threading import Thread
from scripts.main import VintedBot, VintedBotError
import yaml

app = Flask(__name__)

bot_state = {
    "running": False,
    "logs": [],
    "bot": None
}

def validate_config(config):
    """Validate configuration values."""
    required_fields = {
        'login': ['username', 'password'],
        'schedule': ['start_time', 'interval_minutes'],
        'intervals': ['check_live_interval_seconds']
    }
    
    for section, fields in required_fields.items():
        if section not in config:
            raise ValueError(f"Missing required section: {section}")
        for field in fields:
            if field not in config[section]:
                raise ValueError(f"Missing required field: {section}.{field}")

def load_config():
    """Load and validate configuration."""
    try:
        with open('config/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        validate_config(config)
        return config
    except Exception as e:
        raise ValueError(f"Configuration error: {str(e)}")

def log_message(message):
    """Capture log messages with max length limit."""
    MAX_LOGS = 100
    bot_state["logs"].append(message)
    if len(bot_state["logs"]) > MAX_LOGS:
        bot_state["logs"] = bot_state["logs"][-MAX_LOGS:]
    print(message)  # Also log to console for convenience

@app.route("/")
def index():
    """Main page for the GUI. Renders `templates/index.html`."""
    return render_template("index.html")

@app.route("/start-bot", methods=["POST"])
def start_bot():
    """
    Endpoint to start the Vinted bot.
    Expects JSON with `start_time` (e.g. "06:00") and `interval` (int, in minutes).
    """
    if bot_state["running"]:
        return jsonify({"status": "error", "message": "Bot is already running."}), 400

    try:
        config = load_config()
        data = request.json
        start_time = data.get("start_time", config['schedule']['start_time'])
        interval = data.get("interval", config['schedule']['interval_minutes'])

        bot_state["running"] = True
        bot_state["logs"] = []
        bot_state["bot"] = VintedBot()

        def bot_thread():
            try:
                bot_state["bot"].run_bot(start_time, interval, log_message)
            except Exception as e:
                log_message(f"[ERROR] Bot crashed: {str(e)}")
            finally:
                bot_state["running"] = False
                bot_state["bot"] = None

        thread = Thread(target=bot_thread, daemon=True)
        thread.start()
        return jsonify({"status": "success", "message": "Bot started successfully."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/stop-bot", methods=["POST"])
def stop_bot():
    """
    Endpoint to stop the Vinted bot.
    Sets the stop flag on the running bot, which will be checked in run_bot().
    """
    if not bot_state["running"] or not bot_state["bot"]:
        return jsonify({"status": "error", "message": "Bot is not running."}), 400

    try:
        bot_state["bot"].stop()
        return jsonify({"status": "success", "message": "Bot stop signal sent."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/stats")
def get_stats():
    """Returns the bot's statistics, if any."""
    if bot_state["bot"]:
        return jsonify({"status": "success", "stats": bot_state["bot"].stats.get_summary()})
    return jsonify({"status": "error", "message": "Bot not initialized"}), 400

@app.route("/logs")
def get_logs():
    """Endpoint to retrieve current logs from the bot."""
    return jsonify({"status": "success", "logs": bot_state["logs"]})

if __name__ == "__main__":
    # For production, set debug=False. You can also specify a host/port if needed.
    app.run(debug=False)