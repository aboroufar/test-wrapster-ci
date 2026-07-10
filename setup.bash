#!/bin/bash
# shellcheck source=/dev/null

# ---------------------------------------------------------------------------
# .env handling — unset any previously exported vars first so that a re-run
# in the same shell session never inherits stale values, then re-source the
# file and pass it explicitly to every docker compose call via --env-file.
# ---------------------------------------------------------------------------
ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
  # Unset every variable that is currently defined in .env before re-sourcing,
  # so an old exported value cannot shadow the updated one.
  while IFS= read -r line; do
    # Skip blank lines and comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    var_name="${line%%=*}"
    # Strip leading "export " if present
    var_name="${var_name#export }"
    var_name="${var_name// /}"   # trim spaces
    [[ -n "$var_name" ]] && unset "$var_name"
  done < "$ENV_FILE"

  source "$ENV_FILE"
else
  echo "⚠️  Warning: .env file not found."
fi

# --- Variables ---
: "${COMPOSE_PROJ_NAME:="sf_project"}"
WORK_DIR="$PWD"
export CONTAINER_NAME="${CONTAINER_NAME:="${PROJECT_NAME}_container"}"

# Define files for centralized access
MAIN_COMPOSE="docker-compose.yaml"
MONITOR_COMPOSE="monitoring/docker-compose.yaml"

# --env-file is passed explicitly to every docker compose call so that the
# file is always read fresh, regardless of what the shell environment holds.
ENV_FILE_FLAG="--env-file ${ENV_FILE}"

# Convenience alias that includes both compose files + the env-file flag.
ALL_COMPOSE="-f $MAIN_COMPOSE -f $MONITOR_COMPOSE $ENV_FILE_FLAG"

function profile_cmd() {
  local label="$1"; shift
  local start
  start=$(date +%s)
  echo "----------------------------------------------------"
  echo "🚀 Executing: $label"
  "$@"
  local status=$?
  local end
  end=$(date +%s)
  echo "⏱️  Done: $label (Duration: $((end - start))s)"
  echo "----------------------------------------------------"
  return $status
}

# --- STATUS: Simple and Reliable ---
function show_status() {
  echo "📊 Current Environment Status (Project: $COMPOSE_PROJ_NAME)"
  echo "----------------------------------------------------------------------------------------------------"
  printf "%-30s %-12s %-25s %-20s\n" "SERVICE" "STATUS" "PORTS (H:C)" "PROFILES"
  echo "----------------------------------------------------------------------------------------------------"

  local all_services
  all_services=$(docker compose $ALL_COMPOSE --profile "*" config --services 2>/dev/null | sort -u)

  for service in $all_services; do
    local container_id
    container_id=$(docker compose $ALL_COMPOSE -p "$COMPOSE_PROJ_NAME" ps -q "$service" 2>/dev/null)

    local state="stopped"
    local port_mapping="---"

    if [ -n "$container_id" ]; then
      state=$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null)

      port_mapping=$(docker inspect \
        --format '{{range $p, $conf := .NetworkSettings.Ports}}{{range $conf}}{{.HostPort}}:{{$p}} {{end}}{{end}}' \
        "$container_id" 2>/dev/null \
        | tr ' ' '\n' | sed '/^$/d' | sort -u | sed 's/\/tcp//g' | paste -sd ", " -)

      [[ -z "$port_mapping" ]] && port_mapping="none"
    fi

    local profile_list
    profile_list=$(docker compose $ALL_COMPOSE --profile "*" config 2>/dev/null \
      | sed -n "/^  $service:/,/^  [^ ]/p" \
      | grep "profiles:" -A 1 | grep "-" | awk '{print $2}' \
      | tr '\n' ',' | sed 's/,$//')
    [[ -z "$profile_list" ]] && profile_list="default"

    local color="\033[0;31m" # Red
    [[ "$state" == "running" ]] && color="\033[0;32m" # Green

    printf "%-30s ${color}%-12s\033[0m %-25s %-20s\n" "$service" "$state" "$port_mapping" "$profile_list"
  done
  echo "----------------------------------------------------------------------------------------------------"
}

# --- UP: Sequential launch with platform and orphan handling ---
function launch_env() {
  local profile_args=("--profile" "default")
  for p in "$@"; do
    [[ "$p" != "default" ]] && profile_args+=("--profile" "$p")
  done

  cd "$WORK_DIR" || return 1

  # 1. Launch Main Stack first (Creates the network)
  profile_cmd "Building and Starting Main Stack" \
    docker compose -f "$MAIN_COMPOSE" $ENV_FILE_FLAG \
      -p "${COMPOSE_PROJ_NAME}" \
      "${profile_args[@]}" \
      up -d --build --remove-orphans || exit 1

  sleep 2

  # 2. Monitoring Stack
  profile_cmd "Starting Monitoring Stack" \
    env COMPOSE_IGNORE_ORPHANS=True \
    docker compose -f "$MONITOR_COMPOSE" $ENV_FILE_FLAG \
      -p "${COMPOSE_PROJ_NAME}" \
      "${profile_args[@]}" \
      up -d

  echo "⏳ Waiting for containers to stabilize..."
  sleep 5

  # 3. Start Stream Consumer
  if [ "$(docker ps -q -f name=^/${CONTAINER_NAME}$)" ]; then
    profile_cmd "Starting Stream Consumer" \
      docker exec -itd "$CONTAINER_NAME" python -m wrapster.core.scripts.stream_consumer
  else
    echo "❌ Error: $CONTAINER_NAME is not running. Checking logs..."
    docker logs --tail 20 "$CONTAINER_NAME"
    exit 1
  fi
}

mkdocs_server() {
  local mode="$1"

  if [ -z "$mode" ]; then
    echo "❌ Error: 'docs' requires a specific action {serve|build|stop|logs}"
    echo "Usage: $0 docs {serve|build|stop|logs}"
    return 1
  fi

  shift || true
  cd "$WORK_DIR" || return 1

  local compose_cmd=(
    docker compose
    -f "$MAIN_COMPOSE"
    $ENV_FILE_FLAG
    -p "$COMPOSE_PROJ_NAME"
    --profile docs
  )

  case "$mode" in
    build)
      echo "📄 Building MkDocs site (HTML + PDF)..."
      profile_cmd "MkDocs build" \
        /usr/bin/env COMPOSE_IGNORE_ORPHANS=True \
        "${compose_cmd[@]}" run --rm \
        --entrypoint "" \
        -e ENABLE_PDF_EXPORT=1 \
        mkdocs sh -c "mkdocs build --clean --site-dir site"
      echo "✅ Output: ./site/"
      ;;

    serve)
      echo "🌐 Starting MkDocs dev server..."
      profile_cmd "MkDocs serve" \
        env COMPOSE_IGNORE_ORPHANS=True \
        "${compose_cmd[@]}" up -d mkdocs
      echo "📍 http://localhost:${MKDOCS_PORT:-7000}"
      ;;

    stop)
      echo "🔍 Checking if MkDocs is running..."
      local container_id
      container_id=$(docker compose -f "$MAIN_COMPOSE" $ENV_FILE_FLAG \
        -p "$COMPOSE_PROJ_NAME" --profile docs ps -q mkdocs 2>/dev/null)

      # Fixed: was incorrectly comparing State.Status against "true"
      if [ -z "$container_id" ] || \
         [ "$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null)" != "running" ]; then
        echo "❌ Error: MkDocs container is not running."
        echo "💡 Run './setup.bash docs serve' to start it."
        return 1
      fi
      echo "🛑 Destroying MkDocs environment..."
      remove_profile "docs"
      ;;

    logs)
      echo "🔍 Checking if MkDocs is running..."
      local container_id
      container_id=$(docker compose -f "$MAIN_COMPOSE" $ENV_FILE_FLAG \
        -p "$COMPOSE_PROJ_NAME" --profile docs ps -q mkdocs 2>/dev/null)

      if [ -z "$container_id" ] || \
         [ "$(docker inspect -f '{{.State.Running}}' "$container_id" 2>/dev/null)" != "true" ]; then
        echo "❌ Error: MkDocs container is not running."
        echo "💡 Run './setup.bash docs serve' to start it."
        return 1
      fi

      echo "📜 Streaming logs (Ctrl+C to stop)..."
      "${compose_cmd[@]}" logs -f mkdocs
      ;;

    *)
      echo "❌ Error: Invalid MkDocs mode '$mode'"
      echo "Available modes: {serve|build|stop|logs}"
      return 1
      ;;
  esac
}

# --- REMOVE: Surgical removal excluding 'default' ---
function remove_profile() {
  if [ $# -eq 0 ]; then
    echo "❌ Error: 'remove' requires a profile name."
    exit 1
  fi
  cd "$WORK_DIR" || return 1

  local p_flags=()
  for p in "$@"; do p_flags+=("--profile" "$p"); done

  local target_services
  target_services=$(docker compose $ALL_COMPOSE "${p_flags[@]}" config --services)

  local default_services
  default_services=$(docker compose $ALL_COMPOSE --profile default config --services)

  local filtered_services=""
  for service in $target_services; do
    if [[ ! " $default_services " =~ " $service " ]]; then
      filtered_services+="$service "
    fi
  done

  if [ -z "$filtered_services" ]; then
    echo "⚠️  No unique services found for profiles: $*"
    return 0
  fi

  echo "✂️  Targeting ONLY these unique services: $filtered_services"

  profile_cmd "Stopping targeted services" \
    docker compose $ALL_COMPOSE -p "${COMPOSE_PROJ_NAME}" stop $filtered_services

  profile_cmd "Removing targeted containers & volumes" \
    docker compose $ALL_COMPOSE -p "${COMPOSE_PROJ_NAME}" rm -f -v $filtered_services
}

# --- DOWN: Full project wipe ---
function destroy_all() {
  echo "🗑️  Destroying EVERYTHING (all profiles, networks, and volumes)..."
  cd "$WORK_DIR" || return 1
  profile_cmd "Full Compose Down" \
    docker compose $ALL_COMPOSE -p "${COMPOSE_PROJ_NAME}" --profile "*" down -v
}

# --- USER GUIDE / HELP ---
function usage() {
  echo -e "\n📖 \033[1mUSER GUIDE: Setup Script\033[0m"
  echo "----------------------------------------------------"
  echo -e "\033[1mUSAGE:\033[0m"
  echo "  $0 {up|down|remove|status|docs} [profiles...]"
  echo ""
  echo -e "\033[1mCOMMANDS:\033[0m"
  echo -e "  \033[32mup\033[0m      Builds and starts containers."
  echo -e "          \033[3mExample: ./setup.bash up n8n monitoring lab\033[0m"
  echo "          (No commas needed, just list the profiles)"
  echo ""
  echo -e "  \033[31mdown\033[0m    Destroys everything (volumes, networks, all profiles)."
  echo ""
  echo -e "  \033[33mremove\033[0m  Surgically removes specific profiles without touching 'default'."
  echo -e "          \033[3mExample: ./setup.bash remove docs monitoring\033[0m"
  echo ""
  echo -e "  \033[36mstatus\033[0m  Shows real-time status, architecture, and active profiles."
  echo ""
  echo -e "  \033[35mdocs\033[0m    MkDocs management: {serve|build|stop|logs}"
  echo "----------------------------------------------------"
}


# --- Main Logic ---
COMMAND="$1"

if [ -z "$COMMAND" ] || [ "$COMMAND" == "help" ] || [ "$COMMAND" == "--help" ]; then
  usage
  exit 0
fi

shift || true
case "$COMMAND" in
  up)     launch_env "$@" ;;
  remove) remove_profile "$@" ;;
  down)   destroy_all ;;
  status) show_status ;;
  docs)   mkdocs_server "$@" ;;
  *)
    echo "❌ Error: Unknown command '$COMMAND'"
    usage
    exit 1
    ;;
esac