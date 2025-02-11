FROM docker.io/library/rust:1-bookworm as builder
RUN apt-get update \
    && apt-get install -y cmake protobuf-compiler git \
    && rm -rf /var/lib/apt/lists/*
RUN USER=root cargo install cargo-auditable

# Clone the repository instead of copying files
RUN git clone https://github.com/scsibug/nostr-rs-relay.git
WORKDIR ./nostr-rs-relay

# Copy your custom config.toml (this overwrites the default one in the repo)
COPY config.toml ./config.toml

# Build auditable release using locked deps
RUN cargo auditable build --release --locked

FROM docker.io/library/debian:bookworm-slim
ARG APP=/usr/src/app
ARG APP_DATA=/usr/src/app/db
RUN apt-get update \
    && apt-get install -y ca-certificates tzdata sqlite3 libc6 \
    && rm -rf /var/lib/apt/lists/*
EXPOSE 8080
ENV TZ=Etc/UTC \
    APP_USER=appuser
RUN groupadd $APP_USER \
    && useradd -g $APP_USER $APP_USER \
    && mkdir -p ${APP} \
    && mkdir -p ${APP_DATA}
COPY --from=builder /nostr-rs-relay/target/release/nostr-rs-relay ${APP}/nostr-rs-relay
COPY --from=builder /nostr-rs-relay/config.toml ${APP}/config.toml
RUN chown -R $APP_USER:$APP_USER ${APP}
USER $APP_USER
WORKDIR ${APP}
ENV RUST_LOG=info,nostr_rs_relay=info
ENV APP_DATA=${APP_DATA}
CMD ./nostr-rs-relay --db ${APP_DATA} --config config.toml