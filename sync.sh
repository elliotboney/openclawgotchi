#!/bin/bash
# OpenClawGotchi Sync Utility
# Usage: ./sync.sh up   (Local -> Pi)
#        ./sync.sh down (Pi -> Local)

REMOTE="probro@192.168.31.138"
DEST="~/openclawgotchi/"

# Exclude common patterns
EXCLUDES=(
    --exclude '.git'
    --exclude '__pycache__'
    --exclude '.env'
    --exclude '.DS_Store'
    --exclude '*.db'
    --exclude '*.db-journal'
    --exclude 'venv/'
    --exclude 'logs/'
    --exclude 'README_HANDOVER.md'
)

case "$1" in
    up)
        echo "🚀 Pushing local changes to Pi..."
        # Double check: never ever push local .env to production
        rsync -avz "${EXCLUDES[@]}" --exclude='.env' ./ $REMOTE:$DEST || exit 1
        echo "🔄 Restarting bot service..."
        ssh -o StrictHostKeyChecking=no $REMOTE "sudo -n systemctl restart gotchi-bot.service" || exit 1
        echo "✅ Done!"
        ;;
    down)
        echo "📥 Pulling changes from Pi (self-modifications)..."
        rsync -avz "${EXCLUDES[@]}" $REMOTE:$DEST ./ || exit 1
        echo "✅ Done! Local files are now in sync with the bot's mind."
        ;;
    *)
        echo "Usage: $0 {up|down}"
        echo "  up:   Upload code to Pi and restart bot"
        echo "  down: Download code from Pi to local machine"
        exit 1
        ;;
esac
