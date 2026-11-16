# Laboratorios de analise de incidentes

Comparacoes deterministicas de amostras de latencia, isoladas do analisador Python principal.

- Scala 2.13+: scalac labs/scala/IncidentWindow.scala && scala IncidentWindow
- Erlang/OTP com EUnit: erlc -o labs/erlang labs/erlang/incident_aggregator.erl && erl -noshell -pa labs/erlang -eval 'eunit:test(incident_aggregator, [verbose]), halt().'

Os limites sao explicitamente validados. Nenhum servico de producao e iniciado.
