# AI Incident Analyzer

Detector estatístico de anomalias de latência a partir de CSV de logs (`service,latency_ms`), com baseline por serviço e escore z. **Este MVP usa estatística descritiva, não modelo de IA treinado**.

## Estado

**MVP funcional / projeto inicial de portfólio.** Implementa o núcleo descrito abaixo, mas não é produto pronto para produção.

## Como executar

```bash
python analyzer.py examples/latencies.csv
python analyzer.py examples/latencies.csv --threshold 2.3
```

Use `--threshold` para definir o escore z mínimo. O padrão é 2,5 e o valor deve ser positivo e finito. Ajustar o limiar altera a sensibilidade e deve ser validado com dados representativos.

## Testes

```bash
python -m unittest discover -s tests -v
```

O GitHub Actions executa os testes automaticamente em pushes e pull requests.

## Segurança e limitações

Não recebe telemetria remota nem logs com PII. Z-score pode falhar com tendências, picos e distribuição assimétrica; precisa de janela temporal e validação antes de alertas reais.

## Evolução planejada

Integrar coleta OpenTelemetry, Isolation Forest ou modelos apropriados, precisão/recall e dashboard de incidentes.

---
Projeto de Engenharia de Software mantido na conta [juniordev830](https://github.com/juniordev830).

## Análise avançada de incidentes

O comando original `analyzer.py` permanece compatível. Para análise avançada,
utilize `incident_cli.py`, sem dependências externas:

```bash
python incident_cli.py examples/latencies.csv --method mad --min-samples 5
python incident_cli.py examples/latencies.csv --method iqr --format summary
python incident_cli.py examples/latencies.csv --method zscore --format markdown
python incident_cli.py examples/latencies.csv --format sarif --output report.sarif
python incident_cli.py examples/latencies.csv --fail-on critical
python incident_cli.py events.jsonl --input-format jsonl --cooldown-seconds 60
```

Os dados podem conter `service,latency_ms,timestamp,request_id`. As duas primeiras
colunas são obrigatórias. `timestamp` é ISO 8601 com fuso horário e é opcional.
Para JSONL, cada linha deve ser um objeto com os mesmos campos. Linhas inválidas
são contabilizadas por motivo sem imprimir o conteúdo sensível; `--strict`
interrompe na primeira linha inválida.

O motor usa **somente amostras anteriores** à observação para construir a
referência de latência de cada serviço. Para fluxos inteiramente datados,
ordena as observações por instante; nos demais casos mantém a ordem de entrada.
Os métodos disponíveis são desvio absoluto mediano (`mad`), desvio-padrão
(`zscore`) e intervalo interquartil (`iqr`). A janela móvel evita
que dados muito antigos dominem a referência. O cooldown reduz
alertas repetidos de um mesmo serviço, sem descartar amostras do histórico.

O relatório contém contagens de entradas aceitas e rejeitadas, percentis P50,
P95 e P99, tendência entre metades do fluxo, incidentes com IDs estáveis,
pontuação, severidade e localização no arquivo para integração SARIF.

**Códigos de saída:** `0` = processamento válido sem violar a política;
`2` = entrada ou configuração inválida; `3` = incidente igual ou superior
à severidade configurada em `--fail-on`. `--fail-on none` é o padrão.

**Segurança:** processamento exclusivamente local e leitura dos arquivos
fornecidos; não há conexão de rede, coleta remota, execução de comandos ou
aprendizado de máquina. Os relatórios incluem nomes de serviços e métricas,
portanto revise-os antes de publicar. Limites padrão: 20 MiB e 100 mil linhas.
O detector não substitui uma plataforma de observabilidade: distribuições
multimodais, dados ausentes e mudanças de carga podem gerar falsos alertas.

A cobertura automatizada inclui parsing, estatísticas, janelas causais,
ordenamento temporal, cooldown, severidade, filtros, JSON/Markdown/SARIF,
CLI e escrita atômica de relatórios.
