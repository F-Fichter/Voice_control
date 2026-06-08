#!/bin/bash
# Build Docker multi-architecture pour voice-control

set -e

IMAGE_NAME="voice-control"
REGISTRY="${REGISTRY:-}"

build_amd64() {
    echo "=== Build AMD64 ==="
    docker build -f Dockerfile.amd64 -t ${IMAGE_NAME}:amd64 .
    echo "docker tag ${IMAGE_NAME}:amd64 ${IMAGE_NAME}:latest"
}

build_arm64() {
    echo "=== Build ARM64 ==="
    docker build -f Dockerfile.arm64 -t ${IMAGE_NAME}:arm64 .
}

main() {
    echo "=== Voice Control - Docker Build ==="

    if [[ "$1" == "amd64" ]]; then
        build_amd64
    elif [[ "$1" == "arm64" ]]; then
        build_arm64
    else
        # Build les deux si qemu disponible
        if command -v qemu-aarch64-static &> /dev/null; then
            build_amd64
            build_arm64
        else
            echo "Usage: $0 [amd64|arm64]"
            echo "Ou installez qemu pour build multi-architecture"
            exit 1
        fi
    fi
}

main "$@"