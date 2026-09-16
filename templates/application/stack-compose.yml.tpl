services:
  app:
    image: {{IMAGE}}
    restart: unless-stopped
    environment:
      MYTHINGS_ENV_FILE: {{SECRET_MOUNT}}
      MYTHINGS_DATA_DIR: /var/lib/mythings
    volumes:
      - {{SECRET_PATH}}:{{SECRET_MOUNT}}:ro
      - {{DATA_PATH}}/docs:/var/lib/mythings/docs:ro
      - {{DATA_PATH}}/backups:/var/lib/mythings/backups
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.urlopen('{{HEALTH_URL}}')
