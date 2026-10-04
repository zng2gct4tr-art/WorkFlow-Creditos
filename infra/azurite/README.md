# Imagen alternativa local Azurite

La imagen oficial MCR es el valor predeterminado de Compose. Si la red permite npm pero bloquea sus capas, esta receta construye el mismo emulador oficial Azure `azurite@3.35.0` desde npm con lockfile e integridades verificadas mediante `npm ci`.

```bash
docker build -t workflow-azurite:3.35.0 infra/azurite
# Agregar AZURITE_IMAGE=workflow-azurite:3.35.0 a .env
docker compose up -d azurite
```

En redes corporativas, usar argumentos proxy y el secreto BuildKit opcional `environment_ca` con el bundle confiable de la plataforma. No deshabilitar TLS ni integridad. La receta preserva la cuenta aleatoria y volumen definidos por Compose; es exclusivamente para desarrollo. La versión principal de Node está fijada, y producción necesitaría también pinning por digest y revisión de vulnerabilidades. Los paquetes transitivos están fijados por el lockfile.
