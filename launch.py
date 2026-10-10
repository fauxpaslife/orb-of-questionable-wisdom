"""Windows launcher: start the local server, wait for readiness, then open its page."""
import subprocess
import sys
import time
import webbrowser

import httpx

from config import ROOT, PORT

URL = f"http://127.0.0.1:{PORT}"


def ready(client):
    try:
        response = client.get(URL + "/api/state", timeout=1)
        return response.status_code == 200 and response.json().get("app") == "orb-of-questionable-wisdom"
    except (httpx.HTTPError, ValueError):
        return False


def main():
    with httpx.Client(trust_env=False) as client:
        if ready(client):
            webbrowser.open(URL)
            print("The orb is already listening at " + URL)
            return
        process = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT)
        try:
            for _ in range(120):
                if process.poll() is not None:
                    raise RuntimeError(f"The orb server stopped. Check the message above; port {PORT} may be in use.")
                if ready(client):
                    webbrowser.open(URL)
                    print("The orb is listening at " + URL + ". Close this terminal or press Ctrl+C to stop.")
                    process.wait()
                    return
                time.sleep(.25)
            raise RuntimeError("The orb server did not become ready within 30 seconds.")
        except KeyboardInterrupt:
            print("\nThe spirits are going home.")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    main()
