# AI Incident Analyzer

Detector estatístico de anomalias de latência a partir de CSV de logs (`service,latency_ms`), com baseline por serviço e escore z. **Este MVP usa estatística descritiva, não modelo de IA treinado**.

## Estado

**MVP funcional / projeto inicial de portfólio.** Implementa o núcleo descrito abaixo, mas não é produto pronto para produção.

## Como executar

```bash
python analyzer.py examples/latencies.csv
```

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
