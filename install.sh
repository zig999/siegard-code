#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# install.sh — Copia dist/ para <destino>/.claude/
#
# Uso:
#   ./install.sh <caminho-do-projeto-destino>
#
# Comportamento:
#   - Copia e substitui todos os arquivos de dist/ em <destino>/.claude/
#   - NÃO remove arquivos existentes no destino
# ---------------------------------------------------------------------------

DIST_DIR="$(cd "$(dirname "$0")/dist" && pwd)"
DEST_ROOT="${1:-}"

# --- validações -------------------------------------------------------

if [[ -z "$DEST_ROOT" ]]; then
  echo "Uso: $0 <caminho-do-projeto-destino>" >&2
  exit 1
fi

if [[ ! -d "$DIST_DIR" ]]; then
  echo "Erro: diretório dist/ não encontrado em $(dirname "$0")" >&2
  exit 1
fi

DEST_DIR="$DEST_ROOT/.claude"
mkdir -p "$DEST_DIR"

echo "Origem : $DIST_DIR"
echo "Destino: $DEST_DIR"
echo ""

# --- passo 1: copiar/atualizar todos os arquivos de dist/ ----------------

echo "==> Copiando arquivos..."

while IFS= read -r -d '' src_file; do
  rel_path="${src_file#$DIST_DIR/}"
  dest_file="$DEST_DIR/$rel_path"
  dest_subdir="$(dirname "$dest_file")"

  mkdir -p "$dest_subdir"

  if [[ ! -f "$dest_file" ]] || ! cmp -s "$src_file" "$dest_file"; then
    cp "$src_file" "$dest_file"
    echo "  [+] $rel_path"
  fi
done < <(find "$DIST_DIR" -type f -print0)

echo ""
echo "Instalação concluída."
