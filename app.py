"""Ponto de entrada do painel: `streamlit run app.py`.

Fica na raiz porque é o que o Streamlit Cloud procura, e é fino de propósito: o
painel inteiro mora em `src/ciclo_br/painel/`, onde o ruff e o pytest alcançam.
Código de dashboard que vive fora do pacote costuma ser o único do repositório
sem lint e sem teste, e este projeto não tem esse canto.

A linha de `sys.path` existe para que o painel suba a partir de um clone puro,
com `pip install -r requirements.txt` e nada mais. É esse o ambiente do Streamlit
Cloud, que instala o requirements mas não instala o pacote do repositório — sem
isto, `import ciclo_br` falharia lá e em qualquer máquina que não tenha rodado
`pip install -e .`.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ciclo_br.painel.app import main  # noqa: E402  (depende do sys.path acima)

main()
