#!/bin/bash
# GeoVision Lab - Startskript mit automatischer Hardware-Erkennung
# Dieses Skript erkennt automatisch die Plattform und startet den Docker-Stack optimal

set -e

echo "🔍 GeoVision Lab - Hardware-Erkennung..."
echo ""

# Automatische Plattformerkenung
detect_platform() {
    # Check for macOS/Apple Silicon
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "✅ macOS erkannt"
        
        # Check for Apple Silicon
        if [[ "$(uname -m)" == "arm64" ]]; then
            echo "✅ Apple Silicon (M1/M2/M3) erkannt - Optimale Konfiguration wird verwendet"
            echo ""
            echo "📝 Hinweis: Ollama nutzt automatisch die Metal GPU-Beschleunigung"
            echo "apple-silicon"
            return 0
        else
            echo "⚠️  Intel Mac erkannt - CPU-Modus wird verwendet"
            echo "intel-mac"
            return 0
        fi
    fi
    
    # Check for Linux with NVIDIA GPU
    if command -v nvidia-smi &> /dev/null; then
        echo "✅ Linux mit NVIDIA GPU erkannt"
        
        # Check if NVIDIA Container Toolkit is available
        if docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi &> /dev/null; then
            echo "✅ NVIDIA Container Toolkit verfügbar - GPU-Beschleunigung aktiviert"
            echo "nvidia"
            return 0
        else
            echo "⚠️  NVIDIA Container Toolkit NICHT verfügbar"
            echo "   Installation: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
            echo "   CPU-Modus wird verwendet..."
            echo "cpu-only"
            return 0
        fi
    fi
    
    # Default: CPU only
    echo "⚠️  Keine GPU erkannt - CPU-Modus wird verwendet"
    echo "cpu-only"
    return 0
}

# Hauptmenü
show_menu() {
    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║         GeoVision Lab - Startkonfiguration             ║"
    echo "╠════════════════════════════════════════════════════════╣"
    echo "║  1) Auto-Erkennung (Empfohlen)                         ║"
    echo "║  2) Apple Silicon (M1/M2/M3)                           ║"
    echo "║  3) NVIDIA GPU (Linux)                                 ║"
    echo "║  4) CPU-Only (Fallback)                                ║"
    echo "║  5) Beenden                                            ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
}

# Start functions
start_apple_silicon() {
    echo ""
    echo "🚀 Starte GeoVision Lab für Apple Silicon..."
    echo "   (Ollama nutzt automatisch Metal GPU-Beschleunigung)"
    echo ""
    docker compose up --build
}

start_nvidia() {
    echo ""
    echo "🚀 Starte GeoVision Lab mit NVIDIA GPU-Beschleunigung..."
    echo ""
    docker compose -f docker-compose.yml -f docker-compose.nvidia.yml up --build
}

start_cpu_only() {
    echo ""
    echo "🚀 Starte GeoVision Lab im CPU-Modus..."
    echo "   (Hinweis: LLM-Inferenz ist ohne GPU langsamer)"
    echo ""
    docker compose up --build
}

# Interactive mode
interactive_mode() {
    while true; do
        show_menu
        read -p "Bitte wähle eine Option (1-5): " choice
        
        case $choice in
            1)
                platform=$(detect_platform)
                echo ""
                case "$platform" in
                    "apple-silicon") start_apple_silicon "$@" ;;
                    "nvidia") start_nvidia "$@" ;;
                    *) start_cpu_only "$@" ;;
                esac
                break
                ;;
            2)
                start_apple_silicon "$@"
                break
                ;;
            3)
                start_nvidia "$@"
                break
                ;;
            4)
                start_cpu_only "$@"
                break
                ;;
            5)
                echo "👋 Auf Wiedersehen!"
                exit 0
                ;;
            *)
                echo "❌ Ungültige Option. Bitte versuche es erneut."
                ;;
        esac
    done
}

# Command line arguments
MODE="${1:-interactive}"
COMPOSE_ACTION="${2:-up}"

if [[ "$MODE" == "auto" ]]; then
    platform=$(detect_platform)
    case "$platform" in
        "apple-silicon") start_apple_silicon "$COMPOSE_ACTION" ;;
        "nvidia") start_nvidia "$COMPOSE_ACTION" ;;
        *) start_cpu_only "$COMPOSE_ACTION" ;;
    esac
elif [[ "$MODE" == "apple" ]]; then
    start_apple_silicon "$COMPOSE_ACTION"
elif [[ "$MODE" == "nvidia" ]]; then
    start_nvidia "$COMPOSE_ACTION"
elif [[ "$MODE" == "cpu" ]]; then
    start_cpu_only "$COMPOSE_ACTION"
else
    interactive_mode "$COMPOSE_ACTION"
fi
