#!/usr/bin/env bash
# Build and push a NetClaw image compatible with the amd64 EKS node group.
# Usage: deploy/kubernetes/publish-amd64-image.sh <gateway|visual> <tag>
set -euo pipefail

component="${1:-}"
tag="${2:-}"
region="${AWS_REGION:-us-east-1}"
registry="${NETCLAW_ECR_REGISTRY:-637423309390.dkr.ecr.${region}.amazonaws.com}"

if [[ -z "$component" || -z "$tag" ]]; then
  echo "Usage: $0 <gateway|visual> <tag>" >&2
  exit 64
fi

case "$component" in
  gateway)
    repository="netclaw"
    dockerfile="deploy/kubernetes/Dockerfile"
    ;;
  visual)
    repository="netclaw-visual"
    dockerfile="ui/netclaw-visual/Dockerfile"
    ;;
  *)
    echo "Component must be gateway or visual" >&2
    exit 64
    ;;
esac

image="${registry}/${repository}:${tag}"

aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry"
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --file "$dockerfile" \
  --tag "$image" \
  --push \
  .

digest="$(aws ecr describe-images \
  --region "$region" \
  --repository-name "$repository" \
  --image-ids "imageTag=$tag" \
  --query 'imageDetails[0].imageDigest' \
  --output text)"

if [[ "$digest" == "None" || -z "$digest" ]]; then
  echo "ECR did not return a digest for $image" >&2
  exit 1
fi

echo "Published linux/amd64 image: ${registry}/${repository}@${digest}"
echo "Copy that digest into deploy/kubernetes/kustomization.yaml, then run the pre-apply checks."
