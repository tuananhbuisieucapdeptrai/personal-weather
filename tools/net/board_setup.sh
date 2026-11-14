#!/usr/bin/env bash
# Run ON the UNO Q (App Lab terminal or SSH) after it joined the hotspot.
# docs/kickoff-guide.md item 6.
#   bash board_setup.sh                    -> set hostname pw-desk, print network info
#   bash board_setup.sh --static 172.20.10.12/28 172.20.10.1
#                                          -> ALSO pin a static IP (fallback only, see guide)
#   bash board_setup.sh --check-hub <laptop>.local
#                                          -> ALSO test board -> laptop by name (no IP needed)
set -u
NAME=pw-desk
if [ "$(hostname)" != "$NAME" ]; then
  echo "Setting hostname to $NAME (needs sudo)..."
  sudo hostnamectl set-hostname "$NAME" && echo "Done. Reboot later for .local to update: sudo reboot"
else
  echo "Hostname already $NAME"
fi
echo "IP address(es): $(hostname -I)"
echo "Wi-Fi gateway:  $(ip route | awk '/default/ {print $3; exit}')"
if command -v nmcli >/dev/null; then
  CONN=$(nmcli -t -f NAME,TYPE con show --active | awk -F: '$2 ~ /wireless/ {print $1; exit}')
  echo "Active Wi-Fi connection: ${CONN:-none}"
else
  CONN=""; echo "nmcli not found: static IP option unavailable, rely on DHCP + .local"
fi
if [ "${1:-}" = "--static" ]; then
  ADDR="${2:?give address/prefix, e.g. 172.20.10.12/28}"; GW="${3:?give gateway, e.g. 172.20.10.1}"
  [ -n "$CONN" ] || { echo "No active Wi-Fi connection found"; exit 1; }
  echo "Pinning $ADDR via $GW on '$CONN'. Undo with:"
  echo "  sudo nmcli con mod \"$CONN\" ipv4.method auto ipv4.addresses '' ipv4.gateway '' ipv4.dns '' && sudo nmcli con up \"$CONN\""
  sudo nmcli con mod "$CONN" ipv4.method manual ipv4.addresses "$ADDR" ipv4.gateway "$GW" ipv4.dns "$GW" \
    && sudo nmcli con up "$CONN"
  echo "New IP: $(hostname -I)"
fi
if [ "${1:-}" = "--check-hub" ]; then
  HUB="${2:?give the laptop .local name or IP}"
  echo
  if getent hosts "$HUB" >/dev/null; then
    echo "PASS  board resolves $HUB -> $(getent hosts "$HUB" | awk '{print $1}')"
  else
    echo "FAIL  board cannot resolve $HUB (no mDNS on the board?): use the laptop's IP instead"
  fi
  echo "(start tools/net/laptop_check.sh on the laptop first; it listens for 60 s)"
  curl -s -m 5 "http://$HUB:8080/ping" && echo "PASS  board -> laptop:8080" || echo "FAIL  no answer from $HUB:8080"
  echo "Use:  export PW_HUB_URL=http://$HUB:8080"
fi
echo
echo "Write into docs/interfaces.md 0.3:  board IP = $(hostname -I | awk '{print $1}')"
