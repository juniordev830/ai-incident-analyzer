# Guia de validação — AI Incident Analyzer

## Estado e abrangência

Detector de outliers de latência com estatísticas por serviço; não utiliza um modelo de IA treinado.

## Fontes para revisão

`analyzer.py`, `examples/latencies.csv` e `tests/test_analyzer.py`.

## Comandos de verificação

`python -m unittest discover -s tests -v`; `python analyzer.py examples/latencies.csv --threshold 2.3`.

Os testes automatizados devem ser revisados junto do código. Caso não tenham sido executados, registrar essa limitação no PR.

## Matriz de regressão

Tratar amostras únicas, desvio padrão zero, valores não finitos, limite exato do threshold e serviços com pouca observação.

## Próximo incremento fundamentado

Adicionar janelas temporais e métricas de avaliação com amostras sintéticas antes de promover alertas como confiáveis.

## Critérios de contribuição

- [ ] Alteração atende comportamento verificável.
- [ ] Foi criada evidência de teste ou procedimento reproduzível.
- [ ] Nenhuma credencial ou dado pessoal foi versionado.
- [ ] O PR identifica claramente o que mudou e o que ainda falta.
