# ArchUpdater

A simple software manager for Arch Linux, in one window:

- **Installed** – every program and package on the system (official repos, AUR, Flatpak), with filters for programs, things you installed, dependencies/libraries and unused packages. Uninstall removes the app *and* the libraries it brought along, but only those nothing else needs. Core system packages (kernel, drivers, desktop, pacman…) are protected.
- **Get apps** – one search across the official repos, the AUR and Flathub. One click + password to install.
- **Updates** – everything that can be updated, the latest Arch news (with a warning when there's news since your last update), and an **Update everything** button that runs the full safe update:
  1. backs up your configs (`~/.config/hypr`, waybar, rofi, kitty, … kept as the newest 10 `.tar.gz` files),
  2. refreshes mirrors with reflector if the list is more than a day old,
  3. Timeshift snapshot (automatic with `timeshift-autosnap`, otherwise created first),
  4. updates official + AUR packages (`yay -Syu`),
  5. updates Flatpak apps,
  6. optionally removes unused packages and old package files,
  7. checks the Hyprland config, and tells you when a reboot is needed (new kernel or NVIDIA driver).
- **Snapshots** – list, create, delete and **restore** Timeshift snapshots.

The colours come from your Qt theme (qt6ct), so the app follows your wallpaper colours.

## Install

```bash
sudo pacman -S --needed git base-devel
git clone https://github.com/ppcharcoal/archupdater
cd archupdater
makepkg -si
```

Then open **ArchUpdater** from your app launcher, or run `archupdater`.
Shortcuts: `archupdater --updates` opens the Updates page, `archupdater --store` the store.

Every push is built and tested on Arch Linux by GitHub Actions (see the **Actions** tab; the built
package is attached to each run). Pushing a version tag also publishes it as a release:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

After that, the package can be installed straight from the release:

```bash
sudo pacman -U https://github.com/ppcharcoal/archupdater/releases/download/v1.0.0/archupdater-1.0.0-1-any.pkg.tar.zst
```

### Update ArchUpdater itself

```bash
cd archupdater && git pull && makepkg -si
```

### Optional extras

| Package | Enables |
|---|---|
| `yay` (AUR) | AUR search, installs and updates |
| `flatpak` | Flathub apps |
| `timeshift`, `timeshift-autosnap` (AUR) | snapshots, automatic snapshot before updates |
| `reflector` | mirror refresh |

Anything that isn't installed is simply skipped or hidden.

## How it stays safe

- It only ever uses the standard tools (`pacman`, `yay`, `flatpak`, `timeshift`, `reflector`) and their stable output, read with `LC_ALL=C`, so updates to those tools or to Python don't break it. The code lives in `/usr/share/archupdater`, outside Python's version-specific folders.
- Root access goes through polkit and a small helper (`/usr/lib/archupdater/archupdater-root`) that only allows pacman, the reflector service, `paccache` and a few Timeshift actions. Your password is remembered for a few minutes, so one update asks once.
- yay runs as your user and asks for root through the same prompt (`--sudo` points at a shim that only forwards pacman calls).
- Official packages are only updated together with the whole system (Arch doesn't support partial updates). AUR and Flatpak packages can be updated one by one.
- If a step fails, the log is shown and there's a **Try in a terminal** button that runs the same command in a terminal so you can answer any question pacman asks.

## Settings

Stored in `~/.config/archupdater/settings.json` (the checkboxes on the Updates page, the backup folder, which config folders to back up and how many backups to keep).

## Uninstall

```bash
sudo pacman -Rns archupdater
```
