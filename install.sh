#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# install.sh — Sincroniza dist/ para <destino>/.claude/
#
# Uso:
#   ./install.sh <caminho-do-projeto-destino>
#
# Comportamento:
#   - Copia todos os arquivos de dist/ para <destino>/.claude/
#   - Remove do destino arquivos que não existem mais em dist/
#   - NÃO remove arquivos do destino que nunca foram parte de dist/
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

# --- passo 2: remover do destino arquivos que não existem mais em dist/ --

echo ""
echo "==> Removendo arquivos obsoletos..."

removed=0

while IFS= read -r -d '' dest_file; do
  rel_path="${dest_file#$DEST_DIR/}"
  src_file="$DIST_DIR/$rel_path"

  if [[ ! -f "$src_file" ]]; then
    rm "$dest_file"
    echo "  [-] $rel_path"
    ((removed++)) || true
  fi
done < <(find "$DEST_DIR" -type f -print0)

# --- passo 3: limpar diretórios vazios deixados pela remoção -------------

if [[ $removed -gt 0 ]]; then
  find "$DEST_DIR" -mindepth 1 -type d -empty -delete 2>/dev/null || true
fi

echo ""
echo "Instalação concluída."
