AGENT_TOOLSDIRECTORY=/opt/hostedtoolcache
NODE_VERSION="20"

node_arch() {
  case "$(uname -m)" in
    'aarch64') echo 'arm64' ;;
    'x86_64') echo 'x64' ;;
    'armv7l') echo 'armv7l' ;;
    *) exit 1 ;;
  esac
}

IFS=' ' read -r -a NODE <<<"$NODE_VERSION"
for ver in "${NODE[@]}"; do
  printf "\n\t🐋 Installing Node.JS=%s 🐋\t\n" "${ver}"
  VER=$(curl https://nodejs.org/download/release/index.json | jq "[.[] | select(.version|test(\"^v${ver}\"))][0].version" -r)
  NODEPATH="$AGENT_TOOLSDIRECTORY/node/${VER:1}/$(node_arch)"
  mkdir -v -m 0777 -p "$NODEPATH"
  wget "https://nodejs.org/download/release/latest-v${ver}.x/node-$VER-linux-$(node_arch).tar.xz" -O "node-$VER-linux-$(node_arch).tar.xz"
  tar -Jxf "node-$VER-linux-$(node_arch).tar.xz" --strip-components=1 -C "$NODEPATH"
  rm "node-$VER-linux-$(node_arch).tar.xz"
  export PATH="$NODEPATH/bin:$PATH"

  printf "\n\t🐋 Installed Node.JS 🐋\t\n"
  "${NODEPATH}"/bin/node -v

  printf "\n\t🐋 Installed NPM 🐋\t\n"
  "${NODEPATH}"/bin/npm -v
done