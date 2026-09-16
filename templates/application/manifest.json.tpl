{
  "schema_version": "1.0",
  "kind": "{{KIND}}",
  "runtime": "{{RUNTIME}}",
  "app": "{{APP_ID}}",
  "zone": "{{ZONE}}",
  "image": "{{IMAGE}}",
  "artifact": {
    "url": "{{ARTIFACT_URL}}",
    "sha256": "{{ARTIFACT_SHA256}}"
  },
  "install_path": "/srv/nas/stacks/{{ZONE}}/{{APP_ID}}/releases/current/{{APP_ID}}",
  "service_name": "{{APP_ID}}",
  "stack_path": "/srv/nas/stacks/{{ZONE}}/{{APP_ID}}",
  "data_path": "/srv/nas/data/{{APP_ID}}",
  "secret_path": "/srv/nas/secrets/{{APP_ID}}.env",
  "secret_mount": "/run/{{APP_ID}}.env",
  "compose_source": "deploy/bootstrap/stack-compose.yml",
  "required_secrets": ["DATABASE_URL"],
  "generated_secrets": [],
  "healthcheck": {"url": "{{HEALTH_URL}}", "timeout_seconds": 60},
  "migration_command": [],
  "install_command": [],
  "upgrade_command": []
}
