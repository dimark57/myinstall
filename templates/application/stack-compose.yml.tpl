services:
  app:
    image: {{IMAGE}}
    restart: unless-stopped
    environment:
      MYTHINGS_ENV_FILE: {{SECRET_MOUNT}}
    volumes:
      - {{SECRET_PATH}}:{{SECRET_MOUNT}}:ro
