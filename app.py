"""Ponto de entrada do painel: `streamlit run app.py`.

Fica na raiz porque é o que o Streamlit Cloud procura, e é fino de propósito: o
painel inteiro mora em `src/ciclo_br/painel/`, onde o ruff e o pytest alcançam.
Código de dashboard que vive fora do pacote costuma ser o único do repositório
sem lint e sem teste, e este projeto não tem esse canto.
"""

from ciclo_br.painel.app import main

main()
