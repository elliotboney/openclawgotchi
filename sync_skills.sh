#!/bin/bash
# OpenClawGotchi Skills Sync Utility
# Syncs gotchi-skills/ and openclaw-skills/ between local and Pi.
# Needed because openclaw-skills/ is gitignored, so it never travels via git pull.
#
# Usage: ./sync_skills.sh up   (Local -> Pi, then restart bot)
#        ./sync_skills.sh down (Pi -> Local)

REMOTE="eboney@gotchi"
DEST="~/openclawgotchi/"

EXCLUDES=(
    --exclude '.git'
    --exclude '__pycache__'
    --exclude '.DS_Store'
)

SKILL_DIRS=(gotchi-skills openclaw-skills)

case "$1" in
    up)
        echo "🚀 Pushing skills to Pi..."
        for d in "${SKILL_DIRS[@]}"; do
            [ -d "$d" ] && rsync -avz --delete "${EXCLUDES[@]}" "./$d/" "$REMOTE:$DEST$d/" || exit 1
        done
        # echo "🔄 Restarting bot service (skills load at startup)..."
        # ssh -o StrictHostKeyChecking=no $REMOTE "sudo -n systemctl restart gotchi-bot.service" || exit 1
        echo "✅ Done!"
        ;;
    down)
        echo "📥 Pulling skills from Pi..."
        for d in "${SKILL_DIRS[@]}"; do
            rsync -avz --delete "${EXCLUDES[@]}" "$REMOTE:$DEST$d/" "./$d/" || exit 1
        done
        echo "✅ Done! Local skills now match the Pi."
        ;;
    *)
        echo "Usage: $0 {up|down}"
        echo "  up:   Upload gotchi-skills/ + openclaw-skills/ to Pi and restart bot"
        echo "  down: Download both skill dirs from Pi to local"
        exit 1
        ;;
esac
