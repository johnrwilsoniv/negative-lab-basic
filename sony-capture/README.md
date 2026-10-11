# Sony A7 IV tethered capture

Shooting negatives with a tethered Sony A7 IV, straight to `.ARW` on disk for
`nlb` to invert. The repo's Nix dev shell (Linux only) carries the tools:

```sh
nix develop     # from the repo root
```

Commands below are run from this directory; `rolls/` is gitignored.

## Camera setup (do this first)

libgphoto2 only talks to the A7 IV in **PC Remote** mode. In MTP/Mass Storage mode
it enumerates as a different USB device and you get read-only file access, no control.

On the camera: `MENU → Setup → USB → USB Connection Mode → PC Remote`

Also set `MENU → Setup → USB → USB Streaming → Off`. If USB Streaming is on, the
camera enumerates as a UVC webcam (audio + video interfaces, id `054c:0de7`) with
no PTP interface at all, and `gphoto2 --auto-detect` comes back empty.

Then: `MENU → Setup → USB → PC Remote Function`
- `Still Img. Save Dest.` → `PC+Camera` (keeps a card copy as a backup)
- `RAW+J PC Save Img` → `RAW & JPEG` if you want a JPEG proxy per frame

The two USB IDs, if you need to tell modes apart in `lsusb`:

| Mode                 | USB ID      | Notes                          |
|----------------------|-------------|--------------------------------|
| MTP                  | `054c:0da6` | read-only file access          |
| PC Control           | `054c:0da7` | what you want                  |
| USB Streaming (UVC)  | `054c:0de7` | webcam mode, no PTP interface  |

The camera reports itself as `ILCE-7M4` — that's the A7 IV's internal model name.

## Verify the connection

```sh
gphoto2 --auto-detect     # should list "Sony Alpha-A7 IV (PC Control)"
gphoto2 --summary
gphoto2 --list-config     # every property you can read or set
```

## Getting RAW over USB (the important part)

By default the camera sends a **1616x1080 proxy JPEG** over PTP, not the real
frame -- even with the camera set to RAW. Two settings control this:

```sh
gphoto2 --set-config imagequality=RAW        # RAW / RAW+JPEG / JPEG
gphoto2 --set-config pcsaveimgsize=Original  # Original / 2M  <-- the gotcha
```

`pcsaveimgsize` defaults to `2M`. That is what produces the 1616x1080 proxy; until
it is `Original` you will get a small JPEG no matter what else you set. With both
set you get a full 7040x4688 14-bit `.ARW` (~73 MB per frame).

Two related settings that do *not* work over USB, for reference:

- `capturetarget` silently refuses to change (stays `card+sdram`) -- the camera's
  `PC Remote Function → Still Img. Save Dest.` menu wins.
- `pcsaveimgformat` ("RAW+J PC Save Image") is `Readonly: 1`. To transfer RAW *and*
  JPEG together, set `imagequality=RAW+JPEG` and set
  `MENU → Setup → USB → PC Remote Function → RAW+J PC Save Img → RAW & JPEG`
  on the camera itself.

## Capturing a roll

```sh
# Set these once per session, then shoot
gphoto2 --set-config imagequality=RAW --set-config pcsaveimgsize=Original

# Shoot 36 frames, 2s apart, straight to disk — good for a motorized/manual advance
gphoto2 --capture-image-and-download -I 2 -F 36 --filename "rolls/roll01/frame-%03n.%C"

# Or: you press the shutter, gphoto2 downloads each frame as it lands
gphoto2 --capture-tethered --filename "rolls/roll01/frame-%03n.%C"
```

`%C` expands to the real extension, so you get `frame-001.ARW`. At ~73 MB/frame a
36-exposure roll is ~2.6 GB.

Set exposure from the host so it stays identical across the whole roll:

```sh
gphoto2 --set-config /main/capturesettings/f-number=8
gphoto2 --set-config /main/capturesettings/shutterspeed=1/125
gphoto2 --set-config /main/imgsettings/iso=100
```

GUI alternatives for live-view framing and focus: `entangle`, or `darktable`'s
tethering view.

## Inverting negatives

- `nix run .. -- preview rolls/roll01`, then `render` (see the top-level README)
- `darktable` → `negadoctor` module (orange-mask aware; the usual choice for C-41)
- `rawtherapee` → `Film Negative` module
- Scripted: `python3` in this shell has `rawpy` + `numpy` + `pillow`

## Permissions

On NixOS, systemd's `70-uaccess.rules` already tags PTP cameras
(`ID_USB_INTERFACES=="*:060101:*"`) with `uaccess`, so a locally logged-in user
gets access with no extra config.

That tag grants access via the *local seat* only. If you drive the camera over SSH
or from a systemd service, add an explicit rule to your NixOS config:

```nix
services.udev.extraRules = ''
  SUBSYSTEM=="usb", ATTR{idVendor}=="054c", ATTR{idProduct}=="0da7", MODE="0660", GROUP="camera"
'';
users.groups.camera = { };
# and add yourself: users.users.<you>.extraGroups = [ "camera" ];
```

## If gphoto2 says the device is busy

A desktop session's gvfs volume monitor can claim the camera before gphoto2 does:

```sh
gio mount -s gphoto2
pkill -f gvfs-gphoto2-volume-monitor   # if the above isn't enough
```
