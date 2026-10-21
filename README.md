# camtrack – EZVIZ CS-C6N colour/clothing alerts

Watches the camera's RTSP stream, alerts your phone when a chosen colour (e.g. a jacket) appears, and has a web UI to pick the colour, tune sensitivity, draw a detection zone and review sightings.

## 1. Camera setup (EZVIZ app)
1. Same Wi-Fi/LAN as your Mac. Give the camera a fixed IP in your router.
2. Note the **verification code** on the camera's label (RTSP password; user is `admin`).
3. Stream URL: `rtsp://admin:CODE@CAMERA_IP:554/h264/ch1/main/av_stream` (sub-stream: `.../sub/av_stream`).
   Test it first in VLC. If it won't connect, check the EZVIZ app for an RTSP/local-streaming option.

## 2. Run (Mac, Python 3.9+)
    pip install -r requirements.txt
    python3 -m camtrack --host 0.0.0.0 --token YOURSECRET
    # open http://<mac-ip>:8080/?token=YOURSECRET on laptop or phone
    # keep the Mac awake: caffeinate -i python3 -m camtrack ...
Try without a camera: `--source some_video.mp4`.

## 3. Phone notifications (ntfy)
Install the **ntfy** app (Android/iOS), subscribe to a long random topic, and put the same topic in the UI, then "Send test notification". Alerts include a snapshot. The Galaxy Watch receives them via phone notification mirroring.

## Using the UI
- **Click the jacket** in the video to learn its colour; use **Mask view** (target white, rest black) while tuning hue tolerance / saturation / brightness / min size.
- **Drag a zone** to ignore the rest of the frame.
- *Confirm frames* + *cooldown* prevent flicker and notification spam.

## Limits
Colour matching, not identity: anything else in that colour (curtains, a car) matches too. Use the zone, min size and saturation to cut false positives. IR night mode removes colour, so expect daytime-only reliability.
