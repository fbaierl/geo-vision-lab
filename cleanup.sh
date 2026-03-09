#!/bin/bash
# GeoVision Lab - Cleanup Skript
# Entfernt alle Container, Volumes und Images für einen sauberen Neustart

set -e

echo "🧹 GeoVision Lab - Cleanup..."
echo ""

# Container entfernen
echo "📦 Container entfernen..."
docker rm -f geovision-ollama \
    geovision-postgres \
    geovision-pgadmin \
    geovision-ingest \
    geovision-app \
    geovision-loki \
    geovision-promtail \
    geovision-grafana \
    geovision-dozzle 2>/dev/null || echo "   Keine Container zum Entfernen"

# Option: Volumes entfernen (für kompletten Neustart)
if [[ "$1" == "--volumes" ]]; then
    echo "💾 Volumes entfernen..."
    docker volume rm geovision-lab_ollama_data \
        geovision-lab_postgres_data \
        geovision-lab_loki_data \
        geovision-lab_grafana_data 2>/dev/null || echo "   Keine Volumes zum Entfernen"
fi

# Option: Images entfernen
if [[ "$1" == "--images" ]]; then
    echo "🖼️  Images entfernen..."
    docker rmi -f geo-vision-lab-app geo-vision-lab-ingest 2>/dev/null || echo "   Keine Images zum Entfernen"
fi

echo ""
echo "✅ Cleanup abgeschlossen!"
echo ""
echo "Verwendung:"
echo "  ./cleanup.sh            - Nur Container entfernen"
echo "  ./cleanup.sh --volumes  - Container + Volumes entfernen"
echo "  ./cleanup.sh --images   - Container + Images entfernen"
echo "  ./cleanup.sh --all      - Alles entfernen (Container, Volumes, Images)"
echo ""

# Full cleanup option
if [[ "$1" == "--all" ]]; then
    echo "🗑️  Führe vollständige Bereinigung durch..."
    $0 --volumes
    $0 --images
fi
