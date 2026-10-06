# Descompactador em Cascata

Programa em Python que abre um arquivo compactado e, **recursivamente, tudo que aparecer compactado dentro dele** (em qualquer pasta ou subpasta), até não sobrar nada. No final, reúne todos os arquivos numa única pasta, com a opção de manter somente os PDFs.

Vem em duas versões:

| Arquivo | Descrição |
|---|---|
| `descompactador_gui.py` | Versão com interface gráfica, com `.zip`, `.rar`, `.7z` e `.tar*` |
| `descompactar_tudo.py` | Versão simples de linha de comando, somente `.zip` |

## Recursos

- Extração em cascata: ZIP dentro de RAR dentro de 7Z e assim por diante
- Formatos: `.zip`, `.rar`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`
- Aceita um arquivo ou uma pasta inteira como origem
- Junta tudo numa pasta só (sem subpastas) ou mantém a estrutura
- Opção de manter somente arquivos PDF
- Arquivos com nome repetido são renomeados (`nome.pdf`, `nome_1.pdf`, `nome_2.pdf`...)
- Suporte a arquivos com senha
- Corrige acentos em nomes de arquivos de ZIPs criados no Windows
- Proteção contra caminhos maliciosos (*zip slip*) e contra aninhamento infinito
- Os arquivos originais **não são alterados**: toda a extração acontece numa pasta temporária de trabalho

## Requisitos

- Python 3.8 ou superior
- Tkinter (já vem com o Python no Windows e no macOS; no Linux: `sudo apt install python3-tk`)

Dependências opcionais, só para os formatos que você for usar:

```bash
pip install py7zr      # para arquivos .7z
pip install rarfile    # para arquivos .rar
```

Para `.rar`, também é necessário ter o **WinRAR** (`UnRAR.exe`) ou o **7-Zip** instalado. O programa procura os dois nas pastas padrão do Windows.

`.zip` e `.tar*` funcionam sem instalar nada.

## Como usar

### Interface gráfica

```bash
python descompactador_gui.py
```

1. Escolha o arquivo compactado (**Arquivo...**) ou uma pasta com vários (**Pasta...**).
2. Escolha a pasta de saída. Se deixar em branco, será criada `<nome>_extraido` ao lado da origem.
3. Se necessário, informe a senha.
4. Marque as opções desejadas:
   - **Juntar tudo numa pasta só**: sem subpastas (marcado por padrão)
   - **Manter somente arquivos PDF**: descarta os demais arquivos
5. Clique em **Descompactar** e acompanhe o log. No fim, use **Abrir pasta de saída**.

### Linha de comando (somente ZIP)

```bash
python descompactar_tudo.py arquivo.zip
python descompactar_tudo.py arquivo.zip -o C:\saida
python descompactar_tudo.py arquivo.zip --senha 1234
python descompactar_tudo.py arquivo.zip --manter-estrutura
```

## Como funciona

1. Extrai o(s) arquivo(s) de origem para uma pasta temporária.
2. Procura por novos arquivos compactados dentro dela e extrai cada um, repetindo até não sobrar nenhum.
3. Move os arquivos finais para a pasta de saída (aplicando o filtro de PDF, se marcado) e apaga a pasta temporária.

Arquivos que não puderam ser abertos (corrompidos, senha errada, formato sem suporte instalado) são listados no log, e o programa segue com os demais.

## Observações

- Formatos que são ZIP por dentro (`.docx`, `.xlsx`, `.jar`, `.apk`...) **não** são abertos, pois só as extensões listadas acima são tratadas como compactados.
- Há um limite de 100 passadas de aninhamento para evitar loops e *zip bombs*.
- Ao usar **Manter somente arquivos PDF**, todos os outros arquivos são descartados da cópia de trabalho (os originais continuam intactos).

## Licença

Defina a licença do seu projeto (por exemplo, [MIT](https://choosealicense.com/licenses/mit/)).
