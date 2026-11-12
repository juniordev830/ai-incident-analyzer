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

## Guia para contribuir

Veja o [roteiro de testes e manutenção](docs/GUIA_DE_VALIDACAO.md) para validar mudanças com comandos e cenários específicos deste projeto.
