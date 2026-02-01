import subprocess
import json
import yaml
import time
import sys
import os
import requests

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
VERIFIEDGROUP = config["verified_group_id"]
UNVERIFIEDGROUP = config["unverified_group_id"]
ADMIN_CONTACT = config.get("admin_contact")
BOT_NAME = config.get("bot_name", "localis")
BOT_ABOUT = config.get("bot_about", "Your neighborhood watchdog, localis.")
# defaults to empty string if missing, effectively disabling the feature
CARRIER_API_KEY = config.get("carrier_api_key", "")

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

def check_carrier_is_mobile(phone_number):
    if not CARRIER_API_KEY:
        print("   Carrier Check: Disabled (No API Key).")
        return True

    print(f"   Checking carrier for {phone_number}...")

    try:
        response = requests.get(
            "https://phoneintelligence.abstractapi.com/v1/",
            params={"api_key": CARRIER_API_KEY, "phone": phone_number},
            timeout=5
        )

        data = response.json()

        carrier_data = data.get("phone_carrier", {})

        line_type = carrier_data.get("line_type", "Unknown")
        carrier_name = carrier_data.get("name", "Unknown")


        print(f"      Result: Carrier='{carrier_name}', Type='{line_type}'")

        # handle empty/unknown responses by allowing them (Fail Open)
        if not line_type or line_type == "Unknown":
            print("      Type is missing/empty. Allowing.")
            return True

        # strict check: must be explicitly 'mobile'
        if line_type.lower() == "mobile":
            return True
        else:
            return False

    except Exception as e:
        print(f"   Carrier Lookup Exception: {e}")
        return True

def handle_join_request(source):

    # 1. check UUID (Hidden Number) as users can hide their phone number.
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

    # 2. check carrier (Optional)
    # if API key is empty, this returns True immediately.
    if not check_carrier_is_mobile(source):
        print(f"   VoIP or Virtual Number Detected. Rejecting.")
        rejection_msg = (
            "Hi there, it seems you're using a VoIP or Virtual number.\n"
            "To keep our neighborhood safe, we only allow mobile numbers.\n"
            f"If this is an error, please message {ADMIN_CONTACT}."
        )
        run_action_command(["send", "-m", rejection_msg, source])
        return

    # 3. check area code
    area_code = source[2:5] # Assumes +1XXXYYYZZZZ
    if area_code in ALLOWED_AREA_CODES:
        print(f"   Authorized Area Code: {area_code}")
        run_action_command(["send", "-m", "Welcome to the group!", source]) # TODO: make this message more friendly
        run_action_command(["updateGroup", "-g", VERIFIEDGROUP, "-m", source])
    else:
        print(f"   Unauthorized Area Code: {area_code} -> Routing to Unverified Group")
        run_action_command(["send", "-m", "Welcome! You've been added to the group. Please message the admin at " + ADMIN_CONTACT + " to get verified.", source]) # TODO: make this message more friendly
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
