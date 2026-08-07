# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90

LABEL org.opencontainers.image.title="Course target container"
LABEL org.opencontainers.image.description="Minimal Ubuntu 24.04 target for Terraform Docker Provider and Ansible Docker connection verification"
LABEL org.opencontainers.image.base.name="ubuntu:24.04"
LABEL org.opencontainers.image.base.digest="sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        iproute2 \
        net-tools \
        procps \
        python3 \
        python3-apt \
        tar \
    && rm -rf /var/lib/apt/lists/*

CMD ["sleep", "infinity"]
