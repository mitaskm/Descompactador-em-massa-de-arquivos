#!/usr/bin/env python3
"""
Descompactador em cascata (com interface gráfica).

Abre arquivos .zip, .rar, .7z, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz e,
recursivamente, tudo que aparecer compactado dentro deles, até não sobrar
nada. No final junta tudo numa pasta só (opcionalmente apenas os PDFs).

Dependências (só o que você precisar):
    .zip / .tar*  -> já vêm com o Python
    .7z           -> pip install py7zr
    .rar          -> pip install rarfile
                     + ter o WinRAR (UnRAR.exe) ou o 7-Zip instalado

Uso:
    python descompactador_gui.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

EXTENSOES = (".zip", ".rar", ".7z", ".tar.gz", ".tar.bz2", ".tar.xz",
             ".tgz", ".tbz2", ".txz", ".tar")
MAX_PASSADAS = 100  # proteção contra aninhamento infinito / zip bomb


# --------------------------------------------------------------------------
# Núcleo
# --------------------------------------------------------------------------
def eh_compactado(p: Path) -> bool:
    return p.is_file() and p.name.lower().endswith(EXTENSOES)


def nome_base(p: Path) -> str:
    for ext in EXTENSOES:
        if p.name.lower().endswith(ext):
            return p.name[: -len(ext)]
    return p.stem


def caminho_livre(caminho: Path) -> Path:
    """Se já existir, devolve nome_1, nome_2... até achar um livre."""
    if not caminho.exists():
        return caminho
    i = 1
    while True:
        novo = caminho.with_name(f"{caminho.stem}_{i}{caminho.suffix}")
        if not novo.exists():
            return novo
        i += 1


def corrigir_nome(info: zipfile.ZipInfo) -> str:
    """Corrige acentos em ZIPs criados no Windows (nomes em cp437/cp850)."""
    nome = info.filename
    if not (info.flag_bits & 0x800):  # 0x800 = nome já em UTF-8
        try:
            nome = nome.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                nome = nome.encode("cp437").decode("cp850")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return nome.replace("\\", "/")


def _dentro_de(raiz: Path, alvo: Path) -> bool:
    return alvo == raiz or raiz in alvo.parents


def _extrair_zip(caminho: Path, destino: Path, senha: str) -> None:
    pwd = senha.encode() if senha else None
    raiz = destino.resolve()
    with zipfile.ZipFile(caminho) as z:
        for info in z.infolist():
            alvo = (raiz / corrigir_nome(info)).resolve()
            if not _dentro_de(raiz, alvo):
                continue  # caminho suspeito (zip slip)
            if info.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info, pwd=pwd) as src, open(alvo, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _extrair_tar(caminho: Path, destino: Path) -> None:
    raiz = destino.resolve()
    with tarfile.open(caminho) as t:
        seguros = []
        for m in t.getmembers():
            alvo = (raiz / m.name).resolve()
            if _dentro_de(raiz, alvo) and not (m.issym() or m.islnk() or m.isdev()):
                seguros.append(m)
        kwargs = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        t.extractall(destino, members=seguros, **kwargs)


def _extrair_7z(caminho: Path, destino: Path, senha: str) -> None:
    try:
        import py7zr
    except ImportError:
        raise RuntimeError("Para abrir .7z instale o módulo: pip install py7zr")
    with py7zr.SevenZipFile(caminho, password=senha or None) as z:
        z.extractall(destino)


def _configurar_rar(rarfile) -> None:
    """Tenta localizar UnRAR/7-Zip nos locais padrão do Windows."""
    candidatos_unrar = [
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    ]
    candidatos_7z = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    if not shutil.which("unrar"):
        for c in candidatos_unrar:
            if os.path.exists(c):
                rarfile.UNRAR_TOOL = c
                break
    if not shutil.which("7z"):
        for c in candidatos_7z:
            if os.path.exists(c):
                rarfile.SEVENZIP_TOOL = c
                break


def _extrair_rar(caminho: Path, destino: Path, senha: str) -> None:
    try:
        import rarfile
    except ImportError:
        raise RuntimeError("Para abrir .rar instale o módulo: pip install rarfile")
    _configurar_rar(rarfile)
    try:
        with rarfile.RarFile(caminho) as r:
            if senha:
                r.setpassword(senha)
            r.extractall(destino)
    except rarfile.RarCannotExec:
        raise RuntimeError(
            "Para abrir .rar é preciso ter o WinRAR (UnRAR.exe) ou o 7-Zip instalado."
        )


def extrair(caminho: Path, destino: Path, senha: str = "") -> None:
    destino.mkdir(parents=True, exist_ok=True)
    nome = caminho.name.lower()
    if nome.endswith(".zip"):
        _extrair_zip(caminho, destino, senha)
    elif nome.endswith(".rar"):
        _extrair_rar(caminho, destino, senha)
    elif nome.endswith(".7z"):
        _extrair_7z(caminho, destino, senha)
    else:
        _extrair_tar(caminho, destino)


def processar(origem: Path, saida: Path, senha: str, achatar: bool,
              so_pdf: bool, log: Callable[[str], None]) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    temp = saida / "_temp_extracao"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)

    # Arquivos iniciais
    if origem.is_dir():
        iniciais = sorted(
            p for p in origem.rglob("*")
            if eh_compactado(p) and saida.resolve() not in p.resolve().parents
        )
    else:
        iniciais = [origem]
    if not iniciais:
        shutil.rmtree(temp, ignore_errors=True)
        raise RuntimeError("Nenhum arquivo compactado encontrado.")

    falhos: set[Path] = set()
    total = 0

    for arq in iniciais:
        log(f"Extraindo: {arq.name}")
        try:
            extrair(arq, caminho_livre(temp / nome_base(arq)), senha)
            total += 1
        except Exception as e:
            log(f"  [erro] {arq.name}: {e}")

    # Cascata: repete até não sobrar nenhum compactado
    for passada in range(1, MAX_PASSADAS + 1):
        achados = [p for p in temp.rglob("*")
                   if eh_compactado(p) and p not in falhos]
        if not achados:
            break
        log(f"Passada {passada}: {len(achados)} arquivo(s) compactado(s) dentro")
        for z in achados:
            pasta = caminho_livre(z.parent / nome_base(z))
            try:
                extrair(z, pasta, senha)
                z.unlink()
                total += 1
                log(f"  ok: {z.name}")
            except Exception as e:
                falhos.add(z)
                shutil.rmtree(pasta, ignore_errors=True)
                log(f"  [erro] {z.name}: {e}")
    else:
        log(f"Aviso: limite de {MAX_PASSADAS} passadas atingido.")

    # Organização final
    log("Organizando arquivos...")
    qtd = 0
    for arq in list(temp.rglob("*")):
        if not arq.is_file():
            continue
        if so_pdf and arq.suffix.lower() != ".pdf":
            continue
        if achatar:
            destino = caminho_livre(saida / arq.name)
        else:
            destino = caminho_livre(saida / arq.relative_to(temp))
            destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(arq), str(destino))
        qtd += 1
    shutil.rmtree(temp, ignore_errors=True)

    log(f"\nPronto! {total} arquivo(s) compactado(s) aberto(s), "
        f"{qtd} arquivo(s) na saída:\n{saida}")
    if falhos:
        log(f"{len(falhos)} não puderam ser abertos:")
        for f in sorted(falhos):
            log(f"  - {f.name}")


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------
def iniciar_gui() -> None:
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title("Descompactador em cascata")
    root.geometry("760x540")
    root.minsize(640, 460)

    fila: "queue.Queue[tuple[str, str]]" = queue.Queue()
    var_origem = tk.StringVar()
    var_saida = tk.StringVar()
    var_senha = tk.StringVar()
    var_achatar = tk.BooleanVar(value=True)
    var_pdf = tk.BooleanVar(value=False)

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)
    frm.rowconfigure(5, weight=1)

    # Origem
    ttk.Label(frm, text="Origem:").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(frm, textvariable=var_origem).grid(row=0, column=1, sticky="ew", padx=6)
    bts = ttk.Frame(frm)
    bts.grid(row=0, column=2)

    def escolher_arquivo():
        c = filedialog.askopenfilename(
            title="Escolha o arquivo compactado",
            filetypes=[("Compactados", "*.zip *.rar *.7z *.tar *.gz *.tgz *.bz2 *.xz"),
                       ("Todos", "*.*")])
        if c:
            var_origem.set(c)

    def escolher_pasta():
        c = filedialog.askdirectory(title="Escolha a pasta com os compactados")
        if c:
            var_origem.set(c)

    ttk.Button(bts, text="Arquivo...", command=escolher_arquivo).pack(side="left")
    ttk.Button(bts, text="Pasta...", command=escolher_pasta).pack(side="left", padx=(4, 0))

    # Saída
    ttk.Label(frm, text="Saída:").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(frm, textvariable=var_saida).grid(row=1, column=1, sticky="ew", padx=6)

    def escolher_saida():
        c = filedialog.askdirectory(title="Escolha a pasta de saída")
        if c:
            var_saida.set(c)

    ttk.Button(frm, text="Escolher...", command=escolher_saida).grid(row=1, column=2)

    # Senha
    ttk.Label(frm, text="Senha (opcional):").grid(row=2, column=0, sticky="w", pady=4)
    ttk.Entry(frm, textvariable=var_senha, show="*", width=24).grid(
        row=2, column=1, sticky="w", padx=6)

    # Opções
    opc = ttk.Frame(frm)
    opc.grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
    ttk.Checkbutton(opc, text="Juntar tudo numa pasta só (sem subpastas)",
                    variable=var_achatar).pack(anchor="w")
    ttk.Checkbutton(opc, text="Manter somente arquivos PDF",
                    variable=var_pdf).pack(anchor="w")

    # Ações
    acoes = ttk.Frame(frm)
    acoes.grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
    acoes.columnconfigure(2, weight=1)
    btn_iniciar = ttk.Button(acoes, text="Descompactar")
    btn_iniciar.grid(row=0, column=0)
    btn_abrir = ttk.Button(acoes, text="Abrir pasta de saída", state="disabled")
    btn_abrir.grid(row=0, column=1, padx=6)
    barra = ttk.Progressbar(acoes, mode="indeterminate")
    barra.grid(row=0, column=2, sticky="ew", padx=(6, 0))

    # Log
    caixa = ScrolledText(frm, height=12, state="disabled", wrap="word")
    caixa.grid(row=5, column=0, columnspan=3, sticky="nsew")

    def escrever(msg: str):
        caixa.configure(state="normal")
        caixa.insert("end", msg + "\n")
        caixa.see("end")
        caixa.configure(state="disabled")

    def abrir_saida():
        pasta = var_saida.get()
        if not pasta or not os.path.isdir(pasta):
            return
        if hasattr(os, "startfile"):
            os.startfile(pasta)  # Windows
        elif sys.platform == "darwin":
            subprocess.Popen(["open", pasta])
        else:
            subprocess.Popen(["xdg-open", pasta])

    btn_abrir.configure(command=abrir_saida)

    def trabalho(origem, saida, senha, achatar, so_pdf):
        try:
            processar(origem, saida, senha, achatar, so_pdf,
                      log=lambda m: fila.put(("log", m)))
            fila.put(("fim", ""))
        except Exception as e:
            fila.put(("erro", str(e)))

    def iniciar():
        txt = var_origem.get().strip().strip('"')
        if not txt or not Path(txt).exists():
            messagebox.showwarning("Atenção", "Escolha um arquivo ou pasta de origem válido.")
            return
        origem = Path(txt)
        if not var_saida.get().strip():
            base = origem.name if origem.is_dir() else nome_base(origem)
            var_saida.set(str(origem.parent / f"{base}_extraido"))
        saida = Path(var_saida.get().strip().strip('"'))

        caixa.configure(state="normal")
        caixa.delete("1.0", "end")
        caixa.configure(state="disabled")
        btn_iniciar.configure(state="disabled")
        btn_abrir.configure(state="disabled")
        barra.start(12)
        threading.Thread(
            target=trabalho,
            args=(origem, saida, var_senha.get(), var_achatar.get(), var_pdf.get()),
            daemon=True,
        ).start()

    btn_iniciar.configure(command=iniciar)

    def verificar_fila():
        try:
            while True:
                tipo, msg = fila.get_nowait()
                if tipo == "log":
                    escrever(msg)
                else:
                    barra.stop()
                    btn_iniciar.configure(state="normal")
                    if tipo == "fim":
                        btn_abrir.configure(state="normal")
                    else:
                        escrever(f"[erro] {msg}")
                        messagebox.showerror("Erro", msg)
        except queue.Empty:
            pass
        root.after(100, verificar_fila)

    verificar_fila()
    root.mainloop()


if __name__ == "__main__":
    iniciar_gui()