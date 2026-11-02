# Maintainer: ppcharcoal
# Build from a clone of this repository:  makepkg -si
pkgname=archupdater
pkgver=1.1.0
pkgrel=1
pkgdesc="Simple software manager for Arch: installed apps, updates, AUR + Flathub store, AppImages, Timeshift snapshots"
arch=('any')
url="https://github.com/ppcharcoal/archupdater"
license=('MIT')
depends=('python' 'pyside6' 'qt6-svg' 'pacman' 'pacman-contrib' 'polkit')
optdepends=(
  'yay: search and install AUR packages'
  'flatpak: Flathub apps'
  'timeshift: system snapshots'
  'timeshift-autosnap: automatic snapshot before every update'
  'reflector: refresh mirrors before updating'
  'fuse2: needed by most AppImages'
  'kitty: "Try in a terminal" fallback (any terminal works)'
)
source=()
sha256sums=()

package() {
  cd "$startdir"
  install -dm755 "$pkgdir/usr/share/archupdater"
  cp -r --no-preserve=ownership archupdater "$pkgdir/usr/share/archupdater/"
  find "$pkgdir/usr/share/archupdater" -name '__pycache__' -prune -exec rm -rf {} +
  find "$pkgdir/usr/share/archupdater" -type f -exec chmod 644 {} +
  find "$pkgdir/usr/share/archupdater" -type d -exec chmod 755 {} +

  install -Dm755 bin/archupdater "$pkgdir/usr/bin/archupdater"
  install -Dm755 helpers/archupdater-root "$pkgdir/usr/lib/archupdater/archupdater-root"
  install -Dm755 helpers/archupdater-sudo "$pkgdir/usr/lib/archupdater/archupdater-sudo"
  install -Dm644 data/io.github.ppcharcoal.archupdater.policy \
    "$pkgdir/usr/share/polkit-1/actions/io.github.ppcharcoal.archupdater.policy"
  install -Dm644 data/archupdater.desktop "$pkgdir/usr/share/applications/archupdater.desktop"
  install -Dm644 data/archupdater.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/archupdater.svg"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
