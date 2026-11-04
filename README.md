# AI Incident Analyzer

Detector estatístico de anomalias de latência a partir de CSV de logs (`service,latency_ms`). Usa médias e desvio-padrão populacional para calcular escores z **por serviço**; não utiliza um modelo de IA treinado.

## Recursos implementados

- `analyze(rows, threshold=2.5, min_samples=6)`: mantém a API existente para devolver somente as anomalias detectadas.
- `analyze_report(rows, threshold=2.5, min_samples=6)`: retorna anomalias e um diagnóstico por serviço com quantidade de amostras válidas, média, desvio-padrão, disponibilidade do baseline e contagem de anomalias.
- Exibe quantas linhas do CSV foram aceitas ou ignoradas por valores vazios, inválidos, negativos ou não finitos.
- Serviços com menos amostras que o mínimo escolhido aparecem no relatório como **baseline indisponível**; o programa não inventa resultados para eles.
- As saídas são locais e não enviam nenhuma telemetria.

## Como executar

```bash
python analyzer.py examples/latencies.csv
python analyzer.py examples/latencies.csv --threshold 2.3
python analyzer.py examples/latencies.csv --format report
python analyzer.py examples/latencies.csv --format summary --min-samples 6
```

O formato `json` é o padrão anterior: somente `{"anomalies": [...]}`. `--format report` imprime JSON completo com `total_rows`, `accepted_rows`, `ignored_rows`, `threshold`, `min_samples`, `baselines` e `anomalies`. `--format summary` gera texto com os indicadores por serviço. O limiar deve ser positivo e finito, e a quantidade mínima de amostras vai de 2 a 10.000.

## Verificar

```bash
python -m unittest discover -s tests -v
```

O GitHub Actions executa testes com anomalias conhecidas, baselines insuficientes, registros ignorados e saídas dos três formatos da CLI.

## Segurança e limites

Não recebe telemetria remota, não armazena logs com dados pessoais nem executa ações sobre incidentes. O cálculo é uma demonstração, não um detector validado para produção. Z-score pressupõe uma distribuição adequada, pode ser afetado por outliers e não detecta bem tendências, mudanças de baseline ou serviços com amostras insuficientes. Médias e desvios dos relatórios são arredondados para três casas decimais **somente na apresentação**; as decisões de anomalia usam precisão interna.

Próximos passos: janelas temporais, avaliação estatística com dados representativos, OpenTelemetry e dashboard.

Licença ainda não definida.
