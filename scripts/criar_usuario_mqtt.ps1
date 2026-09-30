# Uso: .\scripts\criar_usuario_mqtt.ps1 <usuario> <senha>
# Cria/atualiza o usuário em mosquitto/config/passwd (criando o arquivo se não existir).
# O passwd fica com dono 1883:1883 (usuário mosquitto da imagem) e permissão 0600.
param(
    [Parameter(Mandatory = $true)][string]$Usuario,
    [Parameter(Mandatory = $true)][string]$Senha
)

$cfg = Resolve-Path (Join-Path $PSScriptRoot "..\mosquitto\config")
[string[]]$flag = if (Test-Path (Join-Path $cfg "passwd")) { "-b" } else { "-c", "-b" }

docker run --rm -v "${cfg}:/mosquitto/config" eclipse-mosquitto:2 `
    sh -c 'mosquitto_passwd "$@" && chown 1883:1883 /mosquitto/config/passwd && chmod 0600 /mosquitto/config/passwd' `
    sh @flag /mosquitto/config/passwd $Usuario $Senha
if ($LASTEXITCODE -ne 0) { throw "mosquitto_passwd falhou" }
Write-Host "usuário '$Usuario' gravado em mosquitto/config/passwd"
