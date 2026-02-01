import subprocess
import json
import yaml
import time
import sys
import os

CONFIG_FILE = "config.yaml" # load configuration from config.yaml

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: {CONFIG_FILE} not found.")
        sys.exit(1)

config = load_config()
BOT_NUMBER = config["bot_number"]
ALLOWED_AREA_CODES = config["allowed_area_codes"]
VERIFIEDGROUP= config["real_group_id"]
UNVERIFIEDGROUP = config["decoy_group_id"]
ADMIN_CONTACT = config.get("admin_contact", "the admin")
BOT_NAME = config.get("bot_name", "localis")
BOT_ABOUT = config.get("bot_about", "Your neighborhood watchdog, localis.")

def run_action_command(args):
    # signal-cli receive MUST be closed before calling this.
    cmd = ["signal-cli", "-u", BOT_NUMBER, "--output=json"] + args
    print(f"   [Exec] {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"   Command Failed: {result.stderr.strip()}")
        else:
            print(f"   Success.")
    except Exception as e:
        print(f"   Execution Error: {e}")

def configure_bot():
    # runs the initial profile setup if it hasn't been run before.
    marker_file = ".bot_configured"

    if os.path.exists(marker_file):
        return

    run_action_command(["updateProfile", "--name", BOT_NAME, "--about", BOT_ABOUT])

    # create placeholder marker file so we don't do this every time we restart
    with open(marker_file, "w") as f:
        f.write("configured")

def handle_join_request(source):
    # users can hide their phone number, which is represented as a UUID.
    if not source.startswith("+"):
        print(f"   UUID Detected (Hidden Number).")

        warning_msg = (
            "Your phone number is hidden by your privacy settings.\n\n"
            "If you want to join the main group, you'll need to temporarily set 'Who can see my number' to 'Everyone' in Settings > Privacy, then reply 'join' again.\n\n"
            "Don't worry, you can change it back after you're verified.\n\n"
            "If you'd rather not do that, you can message the admin directly at " + ADMIN_CONTACT
        )

        run_action_command(["send", "-m", warning_msg, source])
        return

    area_code = source[2:5] # Assumes +1XXXYYYZZZZ
    if area_code in ALLOWED_AREA_CODES:
        print(f"   Authorized Area Code: {area_code}")
        run_action_command(["send", "-m", "Welcome to the group!", source]) # placeholder message for testing
        run_action_command(["updateGroup", "-g", VERIFIEDGROUP, "-m", source])

    else:
        print(f"   Unauthorized Area Code: {area_code} -> Routing to Unverified Group")

        run_action_command(["send", "-m", "Welcome! You've been added to the group. Please message the admin at " + ADMIN_CONTACT + " to get verified.", source]) # placeholder message for testing
        run_action_command(["updateGroup", "-g", UNVERIFIEDGROUP, "-m", source])

def main():
    print(f"localis is active @ {BOT_NUMBER}")
    configure_bot()
    print("   Waiting for messages... (Ctrl+C to stop)")

    while True:
        proc = subprocess.Popen(
            ["signal-cli", "-u", BOT_NUMBER, "--output=json", "receive", "--timeout", "-1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            for line in proc.stdout:
                line = line.strip()
                if not line: continue

                try:
                    msg_obj = json.loads(line)

                    envelope = msg_obj.get("envelope", {})
                    source = envelope.get("sourceNumber") or envelope.get("source")
                    data = envelope.get("dataMessage", {})
                    raw_text = data.get("message")
                    text = (raw_text or "").strip()

                    if text: print(f"Message from {source}: {text}")

                    if text and text.lower() == "join":
                        print("   Pausing listener to reply...") # this is because signal-cli receive is blocking, so we need to terminate it to reply
                        proc.terminate()
                        proc.wait()

                        handle_join_request(source)

                        break

                except json.JSONDecodeError:
                    pass

            if proc.poll() is not None:
                stderr = proc.stderr.read()
                if stderr and "LockException" in stderr:
                    time.sleep(1)

        except KeyboardInterrupt:
            print("\nStopping...")
            proc.terminate()
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
